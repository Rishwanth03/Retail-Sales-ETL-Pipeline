# 🛒 Retail Sales ETL Pipeline

> **A production-quality, end-to-end Data Engineering project** built with Python, Pandas, SQLAlchemy, and PostgreSQL — designed for internship portfolios and real-world learning.

---

## 📋 Table of Contents

- [Project Overview](#-project-overview)
- [Architecture](#-architecture)
- [Folder Structure](#-folder-structure)
- [Tech Stack](#-tech-stack)
- [Dataset Description](#-dataset-description)
- [Database Design](#-database-design)
- [Pipeline Phases](#-pipeline-phases)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Execution](#-execution)
- [Testing](#-testing)
- [Power BI Dashboard](#-power-bi-dashboard)
- [Analysis Queries](#-analysis-queries)
- [Future Improvements](#-future-improvements)
- [Author](#-author)

---

## 🎯 Project Overview

The **Retail Sales ETL Pipeline** is a complete data engineering solution that:

| Phase | Description |
|-------|-------------|
| **Extract** | Reads raw CSV files (customers, products, orders, sales) |
| **Validate** | Checks data quality — nulls, duplicates, FK integrity, email format |
| **Transform** | Cleans, enriches, merges datasets, and calculates business KPIs |
| **Load** | Inserts cleaned data into PostgreSQL with upsert logic |
| **Analyse** | Runs 15 SQL business queries and exports results to CSV |
| **Visualise** | Connects Power BI to PostgreSQL for interactive dashboards |

---

## 🏗️ Architecture

```
Raw CSVs (data/raw/)
        │
        ▼
  ┌─────────────┐
  │   EXTRACT   │  scripts/extract.py
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  VALIDATE   │  scripts/validate.py  → data/processed/validation_report.csv
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  TRANSFORM  │  scripts/transform.py → data/cleaned/*.csv
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │    LOAD     │  scripts/load.py      → PostgreSQL (RetailSalesDB)
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  ANALYSIS   │  scripts/analysis.py  → data/processed/analysis/*.csv
  └──────┬──────┘
         │
         ▼
  Power BI Dashboard (dashboard/RetailSales.pbix)
```

---

## 📁 Folder Structure

```
Retail-Sales-ETL/
│
├── README.md                 # Project documentation
├── requirements.txt          # Python dependencies
├── .gitignore                # Git exclusions
├── .env                      # 🔒 Secrets (never commit!)
├── pytest.ini                # Test configuration
│
├── config/
│   └── config.py             # Centralised settings (loads .env)
│
├── data/
│   ├── raw/                  # 📥 Source CSVs
│   │   ├── customers.csv
│   │   ├── products.csv
│   │   ├── orders.csv
│   │   └── sales.csv
│   ├── cleaned/              # 🧹 Post-transform CSVs
│   └── processed/            # 📊 Analysis output CSVs
│
├── database/
│   ├── schema.sql            # PostgreSQL DDL (tables, indexes, FKs)
│   └── create_database.py    # DB initialisation script
│
├── scripts/
│   ├── logger.py             # Logging utility (rotating file + console)
│   ├── helpers.py            # Shared utility functions
│   ├── database.py           # SQLAlchemy engine & connection manager
│   ├── extract.py            # Phase 1 — Read CSV files
│   ├── validate.py           # Phase 2 — Data quality checks
│   ├── transform.py          # Phase 3 — Clean & enrich
│   ├── load.py               # Phase 4 — Load to PostgreSQL
│   ├── analysis.py           # Phase 5 — SQL business queries
│   └── main.py               # 🚀 Pipeline orchestrator
│
├── dashboard/
│   └── RetailSales.pbix      # Power BI dashboard
│
├── notebooks/                # Jupyter EDA notebooks
├── logs/                     # Auto-generated log files
└── tests/
    ├── test_extract.py
    ├── test_transform.py
    ├── test_validate.py
    └── test_helpers.py
```

---

## 🛠️ Tech Stack

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Core language |
| Pandas | 2.2.x | Data manipulation |
| NumPy | 1.26.x | Numerical operations |
| SQLAlchemy | 2.0.x | ORM & DB engine |
| psycopg2 | 2.9.x | PostgreSQL driver |
| PostgreSQL | 15+ | Data warehouse |
| Power BI | Desktop | Dashboards |
| python-dotenv | 1.0.x | Environment management |
| pytest | 8.x | Unit testing |
| Git / GitHub | — | Version control |

---

## 📂 Dataset Description

### customers.csv — 50 records
| Column | Type | Description |
|--------|------|-------------|
| CustomerID | STRING | Primary key (C001–C050) |
| CustomerName | STRING | Full name |
| Email | STRING | Unique contact email |
| Phone | STRING | Phone number |
| City | STRING | Customer city |
| State | STRING | US state |
| Country | STRING | Country (USA) |
| RegistrationDate | DATE | Account creation date |

### products.csv — 50 records across 5 categories
| Column | Type | Description |
|--------|------|-------------|
| ProductID | STRING | Primary key (P001–P050) |
| ProductName | STRING | Display name |
| Category | STRING | Electronics / Sportswear / etc. |
| SubCategory | STRING | Sub-grouping |
| Price | FLOAT | Retail price (USD) |
| Cost | FLOAT | COGS / unit cost (USD) |
| Supplier | STRING | Supplier company |

### orders.csv — 120 orders (Jan–Dec 2023)
| Column | Type | Description |
|--------|------|-------------|
| OrderID | STRING | Primary key (O0001–O0120) |
| CustomerID | STRING | FK → customers |
| OrderDate | DATE | Transaction date |
| PaymentMethod | STRING | Credit Card / PayPal / etc. |

### sales.csv — 223 line items
| Column | Type | Description |
|--------|------|-------------|
| SaleID | STRING | Primary key |
| OrderID | STRING | FK → orders |
| ProductID | STRING | FK → products |
| Quantity | INT | Units purchased |

---

## 🗄️ Database Design

```sql
customers (customer_id PK)
    ↓ (1-to-many)
orders (order_id PK, customer_id FK)
    ↓ (1-to-many)
sales (sale_id PK, order_id FK, product_id FK)
    ↗ (many-to-1)
products (product_id PK)

-- Analytical:
sales_fact (denormalised, all dimensions + metrics)
```

---

## 🔄 Pipeline Phases

### Phase 1 — Extract (`scripts/extract.py`)
- Reads all 4 CSV files using `pandas.read_csv(dtype=str)`.
- Validates file existence and non-emptiness.
- Returns raw DataFrames for downstream processing.

### Phase 2 — Validate (`scripts/validate.py`)
- Checks for: null values, duplicate PKs, invalid emails, negative prices/quantities, future dates, orphaned FKs.
- Exports a `validation_report.csv` if issues are found.

### Phase 3 — Transform (`scripts/transform.py`)
- Strips whitespace, removes duplicates, converts types.
- Renames all columns to `snake_case`.
- Calculates: `TotalAmount`, `Profit`, `ProfitPercentage`.
- Derives: `order_year`, `order_month`, `order_quarter`, `order_weekday`.
- Builds the `sales_fact` denormalised table.

### Phase 4 — Load (`scripts/load.py`)
- Inserts using upsert logic (no duplicates on re-run).
- Loads tables in FK dependency order.
- Rolls back on transaction failure.

### Phase 5 — Analyse (`scripts/analysis.py`)
- Executes 15 SQL business queries against `sales_fact`.
- Exports each result as a CSV.

---

## ⚙️ Installation

### Prerequisites
- Python 3.12+
- PostgreSQL 15+
- pgAdmin 4 (optional, for GUI)
- Power BI Desktop (optional, for dashboards)

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/Retail-Sales-ETL.git
cd Retail-Sales-ETL
```

### 2. Create a Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🔐 Configuration

Edit `.env` with your PostgreSQL credentials:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_NAME=RetailSalesDB
LOG_LEVEL=INFO
```

> ⚠️ **IMPORTANT**: Never commit `.env` to Git. It is already in `.gitignore`.

---

## 🚀 Execution

### Step 1 — Initialise the Database (once)
```bash
python database/create_database.py
```

### Step 2 — Run the Full Pipeline
```bash
python scripts/main.py
```

### Expected Output
```
╔══════════════════════════════════════════════════════╗
║      RETAIL SALES ETL PIPELINE  v1.0.0               ║
╚══════════════════════════════════════════════════════╝
STEP 1 — Database Setup
STEP 2 — Extract (read CSV files)
STEP 3 — Validate (data quality checks)
STEP 4 — Transform (clean & enrich)
STEP 5 — Load (insert into PostgreSQL)
STEP 6 — Analysis (SQL business queries)
✅ Pipeline completed successfully in 8.42s.
```

---

## 🧪 Testing

Run the full test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=scripts --cov-report=term-missing
```

Run a specific test file:
```bash
pytest tests/test_transform.py -v
```

---

## 📊 Power BI Dashboard

### Connection Setup
1. Open **Power BI Desktop**.
2. Click **Get Data → PostgreSQL database**.
3. Enter:
   - Server: `localhost`
   - Database: `RetailSalesDB`
4. Import the `sales_fact` table (and optionally all others).

### Recommended Dashboard Pages

| Page | Visuals |
|------|---------|
| **Overview** | Revenue KPI card, Orders card, Customers card, Profit card |
| **Sales Trends** | Monthly revenue line chart, Quarterly bar chart |
| **Products** | Top 10 products bar, Category pie chart, Profit matrix |
| **Customers** | Top customers bar, Repeat customers table |
| **Geography** | Revenue by state map, Revenue by city bar |

### Recommended Slicers
- Year / Month
- Product Category
- Payment Method
- State

---

## 🔍 Analysis Queries

| # | Query | Description |
|---|-------|-------------|
| 01 | `total_revenue` | Overall Revenue, Profit, Avg Profit % |
| 02 | `total_orders` | Count of distinct orders |
| 03 | `total_customers` | Unique customer count |
| 04 | `avg_order_value` | Mean spend per order |
| 05 | `top_customers` | Top 10 by lifetime spend |
| 06 | `top_products` | Top 10 by revenue |
| 07 | `monthly_revenue` | Revenue by year-month |
| 08 | `revenue_by_category` | Category breakdown |
| 09 | `revenue_by_state` | Geographic revenue |
| 10 | `best_selling_products` | Top 10 by units sold |
| 11 | `lowest_selling_products` | Bottom 10 by units sold |
| 12 | `highest_profit_products` | Top 10 by profit |
| 13 | `repeat_customers` | Customers with > 1 order |
| 14 | `quarterly_revenue` | Q1–Q4 breakdown |
| 15 | `payment_method_analysis` | Orders by payment type |

---

## 🚀 Future Improvements

- [ ] **Apache Airflow** — Schedule pipeline as a DAG with daily/weekly triggers
- [ ] **Docker** — Containerise the full stack (Python + PostgreSQL)
- [ ] **AWS S3** — Move raw data to cloud storage, trigger on S3 events
- [ ] **dbt** — Add data modelling layer on top of PostgreSQL
- [ ] **Great Expectations** — Advanced data quality framework
- [ ] **Alembic** — Database migration management
- [ ] **FastAPI** — REST API to expose analysis results
- [ ] **Grafana** — Real-time pipeline monitoring dashboards

---

## 👨‍💻 Author

**Your Name**
- GitHub: [@yourusername](https://github.com/yourusername)
- LinkedIn: [Your LinkedIn](https://linkedin.com/in/yourprofile)

---

## 📄 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

> ⭐ If this project helped you learn data engineering, please give it a star on GitHub!
