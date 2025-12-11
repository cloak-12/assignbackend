# main.py
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import bcrypt
from jose import jwt, JWTError
from fastapi.middleware.cors import CORSMiddleware


# ===============================
# 1. Environment & DB setup
# ===============================

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
JWT_SECRET = os.getenv("JWT_SECRET", "changeme")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not set in .env")

client = MongoClient(MONGODB_URI)

# master_db holds metadata and admins, like a control plane
master_db = client["master_db"]
orgs_collection = master_db["organizations"]
admins_collection = master_db["admins"]

# orgs_db holds per-organization collections (org_acme, org_tredence, etc.)
orgs_db = client["orgs_db"]

app = FastAPI(
    title="Organization Management Service",
    description="Backend assignment - multi-tenant org management",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===============================
# 2. Helper functions
# ===============================

def get_org_collection_name(org_name: str) -> str:
    """
    Normalize organization name to a collection name.
    E.g. 'Tredence Labs' -> 'org_tredence_labs'
    """
    normalized = org_name.strip().lower().replace(" ", "_")
    return f"org_{normalized}"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(data: dict, expires_minutes: int = 60) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def objectid_to_str(doc: dict) -> dict:
    """
    Convert _id: ObjectId(...) to string so FastAPI can return it as JSON
    """
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc


# ===============================
# 3. Request models (Pydantic)
# ===============================

class CreateOrgRequest(BaseModel):
    organization_name: str
    email: EmailStr
    password: str


class UpdateOrgRequest(BaseModel):
    current_organization_name: str
    new_organization_name: Optional[str] = None
    new_email: Optional[EmailStr] = None
    new_password: Optional[str] = None


class DeleteOrgRequest(BaseModel):
    organization_name: str


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ===============================
# 4. Auth dependency (JWT)
# ===============================

security = HTTPBearer()

def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Extract admin info from JWT.
    Used as a dependency on protected endpoints.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # payload should contain admin_id and organization_name
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ===============================
# 5. Health check
# ===============================

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Org Management Service"}


# ===============================
# 6. Create Organization
# ===============================

@app.post("/org/create")
def create_org(payload: CreateOrgRequest):
    org_name = payload.organization_name.strip()

    # 1. Check if org already exists
    existing = orgs_collection.find_one({"organization_name": org_name})
    if existing:
        raise HTTPException(status_code=400, detail="Organization already exists")

    # 2. Create admin with hashed password
    hashed_pw = hash_password(payload.password)
    admin_doc = {
        "email": payload.email,
        "password": hashed_pw,
        "organization_name": org_name,
        "created_at": datetime.utcnow(),
    }
    admin_result = admins_collection.insert_one(admin_doc)
    admin_id = admin_result.inserted_id

    # 3. Create dynamic collection for the organization
    collection_name = get_org_collection_name(org_name)
    org_collection = orgs_db[collection_name]

    # Optionally initialize collection with a dummy record, then delete
    # This is just to ensure the collection exists and is reachable.
    dummy = {"type": "init_doc", "created_at": datetime.utcnow()}
    init_id = org_collection.insert_one(dummy).inserted_id
    org_collection.delete_one({"_id": init_id})

    # 4. Store org metadata in master_db
    org_doc = {
        "organization_name": org_name,
        "collection_name": collection_name,
        "db_name": "orgs_db",
        "admin_id": admin_id,
        "created_at": datetime.utcnow(),
    }
    orgs_collection.insert_one(org_doc)

    return {
        "message": "Organization created successfully",
        "organization": {
            "name": org_name,
            "collection_name": collection_name,
            "db_name": "orgs_db",
        },
    }


# ===============================
# 7. Get Organization
# ===============================

@app.get("/org/get")
def get_org(organization_name: str = Query(..., description="Name of the organization")):
    org = orgs_collection.find_one({"organization_name": organization_name.strip()})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    return objectid_to_str(org)


# ===============================
# 8. Update Organization
# ===============================

@app.put("/org/update")
def update_org(payload: UpdateOrgRequest, admin=Depends(get_current_admin)):
    """
    For simplicity, we require an authenticated admin,
    and we check they belong to the current_organization_name.
    """
    current_name = payload.current_organization_name.strip()

    # check admin belongs to this org
    if admin.get("organization_name") != current_name:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    org = orgs_collection.find_one({"organization_name": current_name})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    updates = {}

    # handle name change
    if payload.new_organization_name:
        new_name = payload.new_organization_name.strip()
        # ensure new name isn't taken
        existing = orgs_collection.find_one(
            {"organization_name": new_name, "_id": {"$ne": org["_id"]}}
        )
        if existing:
            raise HTTPException(status_code=400, detail="New organization name already in use")

        # rename the org collection (simple approach: copy docs to new collection)
        old_collection_name = org["collection_name"]
        new_collection_name = get_org_collection_name(new_name)

        old_coll = orgs_db[old_collection_name]
        new_coll = orgs_db[new_collection_name]

        # copy docs
        docs = list(old_coll.find())
        if docs:
            new_coll.insert_many(docs)
        # drop old collection
        orgs_db.drop_collection(old_collection_name)

        updates["organization_name"] = new_name
        updates["collection_name"] = new_collection_name

        # also update admin's organization_name in admins collection
        admins_collection.update_many(
            {"organization_name": current_name},
            {"$set": {"organization_name": new_name}},
        )

    # handle email/password updates (admin account)
    # (for simplicity, we update the admin that belongs to this org)
    admin_doc = admins_collection.find_one({"organization_name": current_name})
    if admin_doc:
        admin_updates = {}
        if payload.new_email:
            admin_updates["email"] = payload.new_email
        if payload.new_password:
            admin_updates["password"] = hash_password(payload.new_password)

        if admin_updates:
            admins_collection.update_one(
                {"_id": admin_doc["_id"]}, {"$set": admin_updates}
            )

    if updates:
        orgs_collection.update_one({"_id": org["_id"]}, {"$set": updates})

    updated_org = orgs_collection.find_one({"_id": org["_id"]})
    return {
        "message": "Organization updated",
        "organization": objectid_to_str(updated_org),
    }


# ===============================
# 9. Delete Organization
# ===============================

@app.delete("/org/delete")
def delete_org(
    organization_name: str = Query(..., description="Name of the organization to delete"),
    admin=Depends(get_current_admin),
):
    org_name = organization_name.strip()

    # Only admin of this org can delete
    if admin.get("organization_name") != org_name:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    org = orgs_collection.find_one({"organization_name": org_name})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # drop org collection
    collection_name = org["collection_name"]
    orgs_db.drop_collection(collection_name)

    # delete org metadata
    orgs_collection.delete_one({"_id": org["_id"]})

    # delete admin(s) of this org
    admins_collection.delete_many({"organization_name": org_name})

    return {"message": f"Organization '{org_name}' and related data deleted"}


# ===============================
# 10. Admin Login
# ===============================

@app.post("/admin/login")
def admin_login(payload: AdminLoginRequest):
    admin_doc = admins_collection.find_one({"email": payload.email})
    if not admin_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, admin_doc["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # find org for this admin
    org = orgs_collection.find_one({"admin_id": admin_doc["_id"]})
    org_name = org["organization_name"] if org else admin_doc.get("organization_name")

    token_data = {
        "admin_id": str(admin_doc["_id"]),
        "organization_name": org_name,
    }
    access_token = create_access_token(token_data, expires_minutes=60)

    return {"access_token": access_token, "token_type": "bearer"}
