# P_orders Data Integration Guide

## 1. Overview
This documentation serves as a canonical reference for external applications (e.g., your `.xlsx` ingestion program) targeting the `P_orders` table inside the Amazon Lightsail PostgreSQL database. 

## 2. PostgreSQL Connection Parameters
To connect to the database securely, ensuring compliance with AWS RDS/Lightsail policies, use the following credentials.

| Parameter | Value |
| :--- | :--- |
| **Host** | `ls-a0d9d5db2b9ca903f872a3fb74666a139738a39c.cngosk2ksv87.ap-south-1.rds.amazonaws.com` |
| **Port** | `5432` |
| **Database** | `postgres` |
| **User** | `chummuchdb` |
| **Password** | `chummuchdb555` |
| **SSL Mode** | `require` (CRITICAL: Handshake will fail if not enforced) |

### 2.1 Connection String Templates
Depending on the tech stack of your new program, use the following connection strings:

**Python (SQLAlchemy/psycopg2):**
```python
conn_str = "postgresql+psycopg2://chummuchdb:chummuchdb555@ls-a0d9d5db2b9ca903f872a3fb74666a139738a39c.cngosk2ksv87.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require"
```

**Java (JDBC):**
```java
String url = "jdbc:postgresql://ls-a0d9d5db2b9ca903f872a3fb74666a139738a39c.cngosk2ksv87.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require";
```

**Node.js (pg / Sequelize):**
```javascript
const pool = new Pool({
  connectionString: 'postgresql://chummuchdb:chummuchdb555@ls-a0d9d5db2b9ca903f872a3fb74666a139738a39c.cngosk2ksv87.ap-south-1.rds.amazonaws.com:5432/postgres',
  ssl: {
    rejectUnauthorized: false
  }
});
```

---

## 3. P_orders Table Schema & Mapping Specifications

When mapping data from your `.xlsx` columns to the `P_orders` table, adhere strictly to the target Data Types specified below. The table contains exactly 22 columns with explicit data types.

| PostgreSQL Column Name | PostgreSQL Data Type | Source XLSX Mapping Guidance & Best Practices |
| :--- | :--- | :--- |
| `restaurant_name` | `VARCHAR` | Clean whitespace. E.g. "Pizza Hut" |
| `invoice_no` | `VARCHAR` | Cast to string even if strictly numerical to prevent `.0` float casting. |
| `date` | `DATE` | Standardize format pre-import (e.g., `YYYY-MM-DD`). |
| `kot_no` | `VARCHAR` | Kitchen Order Ticket reference identifier. |
| `payment_type` | `VARCHAR` | Usually categorical: "Cash", "Card", "UPI". Normalize casing. |
| `order_type` | `VARCHAR` | Categorical: "Dine-in", "Takeaway", etc. |
| `status` | `VARCHAR` | E.g. "Completed", "Cancelled". |
| `sub_order_type` | `VARCHAR` | Extension of `order_type`. |
| `area` | `VARCHAR` | Delivery or branch area. |
| `customer_name` | `VARCHAR` | Full name string. Handle possible Null values. |
| `customer_address` | `VARCHAR` | Free text. Clear out newlines (`\n`) and replace them with commas if necessary. |
| `customer_locality` | `VARCHAR` | Neighborhood string. |
| `my_amount` | `NUMERIC(10, 2)` | Base item amount. Exclude currency symbols. Ensure parseable as numeric. |
| `total_tax` | `NUMERIC(10, 2)` | Computed tax amount. |
| `discount` | `NUMERIC(10, 2)` | Discount applied. |
| `delivery_charge` | `NUMERIC(10, 2)` | Delivery fees. |
| `container_charge` | `NUMERIC(10, 2)` | Packing/material charge. |
| `service_charge` | `NUMERIC(10, 2)` | Mandatory service charges. |
| `additional_charge` | `NUMERIC(10, 2)` | Any extraneous charges mapped here. |
| `waived_off` | `NUMERIC(10, 2)` | Adjustments. |
| `round_off` | `NUMERIC(10, 2)` | Fractional roundoff correction. |
| `total` | `NUMERIC(10, 2)` | Final gross total amount. |

---

## 4. Import Pitfalls and Idempotency Notes

### 4.1 Missing Primary Key Constraints
Currently, the `P_orders` table does **not** have a strict `UNIQUE` or `PRIMARY KEY` enforced.
- **Risk:** Re-running your loading pipeline without cleaning the table could result in **Duplicate Data**.
- **Solution:** In your ingestion script, ensure an upsert/merge logic is applied based on a unique composite key (such as `invoice_no` + `date`), or TRUNCATE/DELETE specific timeframe boundaries before running `df.to_sql(..., if_exists='append')`.

### 4.2 Excel `NaN` vs `NULL`
If the data source is loaded via Pandas:
- Excel blank cells convert to `NaN` floats or `NaT` objects.
- PostgreSQL will reject python `NaN`.
- Ensure you perform a fill transformation (e.g., `df = df.fillna('')` or `df = df.where(pd.notnull(df), None)`) before firing the `INSERT` payload so `NULL` values correctly convert to Postgres NULLs or empty strings.

### 4.3 Sanitization Hooks
Before inserting, standardize all column names into lowercase format and map them precisely. Extensively clean characters: spaces, `#`, `%`, `&` should not be present in the DataFrame series names mapping into SQL columns.

## 5. Summary Check-list for Production Script
- [ ] Ensure `.xlsx` header columns are stripped and precisely map to the list seen in Section 3.
- [ ] Connect with explicit `sslmode=require`.
- [ ] Ensure currency/number columns are clean of prefix strings (like ₹ or $) to map to `NUMERIC(10, 2)` and parse dates properly using Pandas `.to_datetime()` before load.
- [ ] Have a strategy to handle duplicates since `P_orders` does not enforce referential constraints itself right now.
