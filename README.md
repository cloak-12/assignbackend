# 🏢 Organization Management Service – Backend

Multi-tenant organization management system built using **FastAPI + MongoDB** for the Tredence assignment.

-----------------------------------------------------------
🔥 Features
-----------------------------------------------------------
- Create organizations dynamically
- Auto admin creation with hashed password
- Admin login using JWT Authentication
- Update organization details (name/email/password)
- Delete organization & its database collection
- Fetch organization details from master DB
- Multi-tenant DB architecture with dynamic collections

-----------------------------------------------------------
🛠 Tech Stack
-----------------------------------------------------------
- Python
- FastAPI
- MongoDB Atlas
- JWT (python-jose)
- Bcrypt
- Pydantic
- Uvicorn

-----------------------------------------------------------
📂 Folder Structure
-----------------------------------------------------------
tredence-backend/
│── main.py
│── .env
│── README.md
└── venv/

-----------------------------------------------------------
⚙ Setup Instructions
-----------------------------------------------------------
1. Create Virtual Environment
   python -m venv venv
   venv\Scripts\activate  (Windows)
   source venv/bin/activate (Mac/Linux)

2. Install Dependencies
   pip install fastapi uvicorn pymongo python-dotenv bcrypt "python-jose[cryptography]" email-validator

3. Add .env file
   MONGODB_URI=<your_mongodb_uri>
   JWT_SECRET=<your_secret_key>
   JWT_ALGORITHM=HS256

4. Run Server
   uvicorn main:app --reload

Visit:
http://127.0.0.1:8000/       -> Health
http://127.0.0.1:8000/docs   -> Swagger API Docs

-----------------------------------------------------------
📌 API Endpoints
-----------------------------------------------------------
GET     /                     -> Health check
POST    /org/create           -> Create organization + admin
POST    /admin/login          -> Login admin & receive JWT
GET     /org/get              -> Get organization details
PUT     /org/update           -> Update org/admin details (requires token)
DELETE  /org/delete           -> Delete org (requires token)

-----------------------------------------------------------
🧪 Sample Requests
-----------------------------------------------------------

Create Organization (POST /org/create)
{
  "organization_name": "Tredence Demo",
  "email": "admin@tredence.com",
  "password": "Admin@123"
}

Admin Login (POST /admin/login)
{
  "email": "admin@tredence.com",
  "password": "Admin@123"
}
--> Use token as:  Bearer <ACCESS_TOKEN>

Update Organization (PUT /org/update)
{
  "current_organization_name": "Tredence Demo",
  "new_organization_name": "Tredence Global",
  "new_email": "newadmin@tredence.com",
  "new_password": "NewAdmin@123"
}

Delete Organization
DELETE /org/delete?organization_name=Tredence Global

-----------------------------------------------------------
🧠 Architecture
-----------------------------------------------------------
master_db/
│── organizations       -> Org metadata
└── admins              -> Admin users

orgs_db/
│── org_tredence_demo   -> Dynamic org collections
└── org_<any_org_name>  -> Created on demand

-----------------------------------------------------------
📄 Summary
-----------------------------------------------------------
✔ Backend functional & tested
✔ JWT authentication implemented
✔ CRUD operations complete
✔ Ready for frontend integration
