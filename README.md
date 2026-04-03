# 🏦 Banking Customer Management System — Blueprint & Documentation

Welcome to the **Banking Customer Management System**, a highly robust, compliance-driven backend application built with Python. This project is meticulously crafted to simulate real-world banking environments, enforcing strict financial compliance, data security, and monetary precision.

This Readme serves as a comprehensive guide for developers, product managers, and auditors to understand **what** was built, **how** it works, and **why** certain architectural decisions were made.

---

## 🏗️ 1. Technical Stack & Libraries Used

The project relies on a modern, high-performance Python stack. Here is a breakdown of the core libraries and **why** they are crucial to the system:

| Library | Purpose & Importance |
| :--- | :--- |
| **FastAPI** | The core web framework. Chosen for its automatic Swagger UI generation, extreme performance (via Starlette/Pydantic), and intuitive dependency injection which is heavily used for Role-Based Access Control (RBAC). |
| **SQLAlchemy** | The Object-Relational Mapper (ORM). It abstracts raw SQL, allowing us to safely interface with the database using Python objects. It seamlessly handles transitions from local SQLite to production-grade PostgreSQL. |
| **Pydantic** | Used for data validation. Every incoming request and outgoing response passes through Pydantic schemas, ensuring missing or invalid data (like empty names or negative money amounts) never touches the core logic. |
| **Passlib (Bcrypt)** | Handles password hashing. We never store plain-text passwords. Bcrypt is a computationally heavy cryptographic algorithm designed to thwart brute-force and rainbow table attacks. |
| **Cryptography (Fernet)** | Used for symmetric encryption. Used specifically to encrypt highly sensitive Personally Identifiable Information (PII) like National ID strings before they enter the database. |
| **python-jose (JWT)** | Manages JSON Web Tokens. It allows the system to securely identify who is making a request and what role (`TELLER`, `MANAGER`, `ADMIN`) they hold without continuously querying the database for credentials. |

---

## 🧠 2. Core Modules & Business Logics

The application is divided into heavily guarded operational domains. Below is an explanation of the deeply integrated banking logics.

### A. Security & Authentication (`models/auth.py`)
* **Role-Based Access Control (RBAC):** Users are divided naturally into `CUSTOMER`, `TELLER`, `MANAGER`, and `ADMIN`. A regular Teller can open an account, but cannot delete a customer or approve a loan—those require Manager or Admin clearance.
* **Brute-Force Lockouts:** If an attacker tries to guess a password and fails **3 times consecutively**, the system logs the attempts and dynamically locks the account for **15 minutes**.

### B. Customer Onboarding & KYC (`models/customer.py`)
* **Age Verification:** The logic mathematically verifies the applicant's Date of Birth against the current server date. Anyone under **18 years old is strictly rejected**.
* **Duplicate Identity Protection:** To ensure one human doesn't open multiple fragmented profiles, we store a **SHA-256 Hash** of their National ID. Hashes cannot be decrypted, but they allow the database to easily flag if the exact same ID is submitted twice.
* **Encrypted Storage:** While the hash handles duplicates, the actual National ID is encrypted tightly using a `Fernet` symmetric key. If the database is stolen, hackers cannot read the IDs.
* **KYC Lifecycle:** Profiles start as `PENDING`. Until a Manager explicitly elevates the status to `VERIFIED`, the system blocks the customer from opening accounts or applying for loans.

### C. Account Management (`models/account.py`)
* **PAISE-Based Architecture (Crucial):** **Floating-point math in programming is flawed** (e.g., `0.1 + 0.2 = 0.30000000000000004`). Because of this, dealing with decimals for money is dangerous. Our entire system operates exclusively in integers using **Paise (100th of an INR)**. `₹500` is stored fundamentally as `50000`.
* **Account Ceilings & Floors:**
    * **Savings:** Requires a ₹1,000 minimal footprint. Daily aggregate withdrawals are restricted to ₹50,000.
    * **Current:** Requires a ₹5,000 minimal footprint. Daily aggregate withdrawals are restricted to ₹2,00,000.
    * Withdrawals uniquely calculate against these thresholds. If you have ₹1,500 in a Savings account, a request to withdraw ₹600 is gracefully rejected (`422 Error`) because it would dip the account to ₹900, violating the minimum threshold rules.

### D. Transactions & Audit Trails (`models/transaction.py`)
* **Immutable Audit Logs:** Banking thrives on tracking. Any time a user opens an account, a Manager verifies KYC, or an Admin updates a status, an entry is written directly to the `audit_logs` table. **Audit logs completely lack a DELETE or UPDATE method.** They are permanent.
* **Failed Transaction Logging:** When a transaction fails (e.g., due to limits or insufficient balance), the attempt is recorded with specialized error codes. This is critical for banks to identify suspicious behavior or fix recurring user mistakes.
* **Transfers:** Verified internal transfers securely decrement the source account while inflating the paired receiving account in a single isolated swoop.

### E. Loan Processing & Amortization (`models/loan.py`)
* **Eligibility Matrices:** You cannot acquire a loan randomly. The logic demands your linked account must represent `ACTIVE` status, reflect at least `6 months` of age, and your Customer KYC must evaluate as `VERIFIED`. Your credit score must also be rigidly `> 650`.
* **Standard Amortization EMI Equations:** The system uses standard banking mathematical formulas to structure your payback terms. It natively maps out your `Principal Components` vs `Interest Components`, pre-generating an entire schedule of EMI dates.

### F. Compliance Middleware (AML & CTR)
* **Anti-Money Laundering (AML):** Any single transaction moving over **₹10,00,000** triggers an automated AML Flag.
* **Currency Transaction Reports (CTR):** Any raw 'cash' transaction (deposits/withdrawals, excluding internal digital transfers) evaluating over **₹50,000** generates a specialized CTR report.
* *Importance:* In the real world, standard banking regulatory authorities (like FINCEN or the RBI) mandate these automated flags to combat severe corporate financing fraud or illicit market money movement. 

---

## 📂 3. Project Structure

```text
banking_app/
├── main.py                  # The engine. Configures the database and binds all routes.
├── database.py              # Houses the SQLAlchemy pipeline logic connecting to the DB.
├── generate_env.py          # A python script that auto-generates crypto-keys and the .env file.
├── schemas/                 # Pydantic validation files. If it enters/leaves the API, it checks here first.
├── models/                  # The Database Tables structures dictating columns and relationships.
├── services/                # The Brains. All heavy banking logic, math, and rules live here.
├── routes/                  # The API HTTP Endpoints (GET, POST, DELETE) that trigger the services.
├── utils/                   # Small repetitive math helpers and unique ID generators.
└── middleware/              # Security barriers handling tokens, RBAC, and background audit triggers.
```

---

## 🚀 4. Setup & Running the Application

### Step 1: Environment & Requirements
Ensure you are using **Python 3.10+**. 
Create a virtual environment and install dependencies:
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 2: Key Generation & Security
You must generate heavy cryptographic keys to bind JWT Auth and Fernet Encryption securely. Run the built-in generation script:
```bash
python generate_env.py
```
*(This automatically creates an `.env` file containing everything the server needs).*

### Step 3: Boot The Application
Boot the server using the `uvicorn` ASGI web-server:
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🧪 5. Testing the Project visually via Swagger UI

FastAPI provides an incredible, interactive graphical dashboard allowing you to click, deploy, and verify every piece of logic cleanly from a browser without knowing terminal commands.

**1. Open The UI:** Visit 👉 **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**  
*(You will see all routes organized by their structural domain)*

**2. Authenticate the Engine:**
Upon first boot, the system securely creates a superuser.
* Click the green **Authorize** button at the top right of the page.
* Type **Username:** `admin` | **Password:** `admin1234`
* Click **Authorize**, then **Close**. Notice the locked little padlocks denoting you are actively signed in.

**3. Try Generating a Customer Profile:**
* Scroll to the **Customers (KYC)** block, expand **`POST /api/customers/`**.
* Click **Try it out** and replace the payload block with raw JSON logic:
```json
{
  "full_name": "Ravi Kumar",
  "date_of_birth": "1990-05-15",
  "national_id": "AADHAR-987823485",
  "address": "12/A, Tech Hub, Pune",
  "phone": "9876543210",
  "email": "ravi.kumar@example.com"
}
```
* Click **Execute**. Review the `201 Response`. Grab that specific user `id` (likely `1`) for the next step!

**4. Approve their application:**
* Customers can't conduct business while `PENDING`. Open **`PATCH /api/customers/{customer_id}/kyc`**.
* Enter ID `1` into the parameter field. Modify the payload explicitly to `{"status": "VERIFIED"}`. Execute it.

**5. Test a Deletion Security Restriction:**
* Open **`DELETE /api/customers/{customer_id}`**. 
* Run ID `1` through. Because the user has no linked accounts tying up the bank, the interface will proudly declare the account cleanly wiped with a `200` response block.

**6. Test the Minimal Threshold Banking Limits:**
* Remake your test Customer utilizing step 3. 
* Open **`POST /api/accounts/`**. Let's deposit exactly ₹1,500 (`150000` paise). 
```json
{
  "customer_id": 1,
  "account_type": "SAVINGS",
  "opening_balance_paise": 150000
}
```
* Run it. Now open the Transactions withdrawal block at **`POST /api/transactions/withdraw`**.
* Demand a ₹600 extraction (`60000` paise). 
* Notice the system absolutely rejects the API call with a `422 Unprocessable Entity` error explicitly noting that dropping the wallet by ₹600 violates your mandatory ₹1,000 protective minimum balance!

---
*Developed as a highly robust backend blueprint to demonstrate standard real-world banking logic applications using Python.*
