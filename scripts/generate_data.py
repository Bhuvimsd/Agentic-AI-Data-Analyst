"""
scripts/generate_data.py
-------------------------
Deterministic synthetic e-commerce dataset generator for Agentic AI Data Analyst.
Uses a fixed random seed (42) and realistic Indian business contexts:
- Indian cities and store locations across regions
- INR product pricing with realistic category distributions
- Completed, Pending, and Cancelled orders with historical order item unit prices
- Consistent payment records with intentional edge cases for anomaly detection
"""

import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Tuple
from faker import Faker

# Fixed seed for 100% reproducible data generation
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
Faker.seed(RANDOM_SEED)
fake = Faker(["en_IN"])

# ------------------------------------------------------------------------------
# Realistic Master Data Definitions
# ------------------------------------------------------------------------------
INDIAN_CITIES = [
    "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai",
    "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Surat",
    "Lucknow", "Chandigarh", "Kochi", "Indore", "Coimbatore"
]

STORES_MASTER = [
    {"store_id": 1, "store_name": "Bengaluru Indiranagar Flagship", "region": "South"},
    {"store_id": 2, "store_name": "Hyderabad Banjara Hills Store", "region": "South"},
    {"store_id": 3, "store_name": "Chennai T Nagar Hub", "region": "South"},
    {"store_id": 4, "store_name": "Mumbai Bandra West Store", "region": "West"},
    {"store_id": 5, "store_name": "Pune Koregaon Park Store", "region": "West"},
    {"store_id": 6, "store_name": "Delhi Connaught Place Store", "region": "North"},
    {"store_id": 7, "store_name": "Chandigarh Sector 17 Store", "region": "North"},
    {"store_id": 8, "store_name": "Kolkata Park Street Store", "region": "East"},
    {"store_id": 9, "store_name": "Indore Vijay Nagar Store", "region": "Central"},
]

PRODUCTS_MASTER = [
    # Electronics
    {"product_id": 1, "product_name": "Noise-Cancelling Wireless Headphones", "category": "Electronics", "price": Decimal("8499.00")},
    {"product_id": 2, "product_name": "Smart Fitness Band Pro", "category": "Electronics", "price": Decimal("3299.00")},
    {"product_id": 3, "product_name": "4K Ultra-HD Smart LED TV 55-inch", "category": "Electronics", "price": Decimal("42999.00")},
    {"product_id": 4, "product_name": "Mechanical Gaming Keyboard RGB", "category": "Electronics", "price": Decimal("4599.00")},
    {"product_id": 5, "product_name": "Ergonomic Wireless Optical Mouse", "category": "Electronics", "price": Decimal("1299.00")},
    {"product_id": 6, "product_name": "Fast-Charging Power Bank 20000mAh", "category": "Electronics", "price": Decimal("1999.00")},
    # Apparel
    {"product_id": 7, "product_name": "Premium Cotton Casual Slim Shirt", "category": "Apparel", "price": Decimal("1499.00")},
    {"product_id": 8, "product_name": "Relaxed Fit Denim Jeans", "category": "Apparel", "price": Decimal("2299.00")},
    {"product_id": 9, "product_name": "Breathable Athletic Running Shoes", "category": "Apparel", "price": Decimal("3499.00")},
    {"product_id": 10, "product_name": "Traditional Handcrafted Kurta Set", "category": "Apparel", "price": Decimal("2799.00")},
    {"product_id": 11, "product_name": "Lightweight Waterproof Windbreaker", "category": "Apparel", "price": Decimal("2199.00")},
    # Home & Kitchen
    {"product_id": 12, "product_name": "Stainless Steel Induction Cookware Set", "category": "Home & Kitchen", "price": Decimal("4999.00")},
    {"product_id": 13, "product_name": "Automatic Espresso Coffee Maker", "category": "Home & Kitchen", "price": Decimal("12499.00")},
    {"product_id": 14, "product_name": "Cold-Press Slow Masticating Juicer", "category": "Home & Kitchen", "price": Decimal("7899.00")},
    {"product_id": 15, "product_name": "Ceramic Non-Stick Frying Pan 28cm", "category": "Home & Kitchen", "price": Decimal("1699.00")},
    {"product_id": 16, "product_name": "Orthopedic Memory Foam Pillow", "category": "Home & Kitchen", "price": Decimal("1899.00")},
    # Grocery & Gourmet
    {"product_id": 17, "product_name": "Organic Extra Virgin Olive Oil 1L", "category": "Grocery", "price": Decimal("1250.00")},
    {"product_id": 18, "product_name": "Single-Origin Roasted Coffee Beans 500g", "category": "Grocery", "price": Decimal("750.00")},
    {"product_id": 19, "product_name": "Premium California Raw Almonds 1kg", "category": "Grocery", "price": Decimal("990.00")},
    {"product_id": 20, "product_name": "Assorted Darjeeling Green Tea Box", "category": "Grocery", "price": Decimal("599.00")},
    # Fitness & Outdoors
    {"product_id": 21, "product_name": "High-Density Non-Slip Yoga Mat", "category": "Fitness", "price": Decimal("1199.00")},
    {"product_id": 22, "product_name": "Adjustable Dumbbell Set 20kg", "category": "Fitness", "price": Decimal("5499.00")},
    {"product_id": 23, "product_name": "Insulated Stainless Steel Hydration Flask 1L", "category": "Fitness", "price": Decimal("899.00")},
    # Intentionally Never Ordered Products (for query testing)
    {"product_id": 24, "product_name": "Vintage Turntable Vinyl Record Player", "category": "Electronics", "price": Decimal("18999.00")},
    {"product_id": 25, "product_name": "Titanium Expedition Camping Stove", "category": "Fitness", "price": Decimal("14500.00")},
]

ORDER_STATUSES = ["Completed", "Pending", "Cancelled"]
STATUS_WEIGHTS = [0.82, 0.10, 0.08]  # Realistic e-commerce distribution

PAYMENT_METHODS = ["UPI", "Credit Card", "Debit Card", "Net Banking", "Cash on Delivery"]
PAYMENT_METHOD_WEIGHTS = [0.45, 0.25, 0.15, 0.10, 0.05]


def generate_synthetic_dataset(
    num_customers: int = 500,
    num_orders: int = 2200,
    seed: int = RANDOM_SEED
) -> Dict[str, List[dict]]:
    """
    Generates deterministic, relationally consistent synthetic dataset.
    Returns a dictionary of lists: customers, products, stores, orders, order_items, payments.
    """
    # Explicitly reset seeds to guarantee identical results on repeated calls
    random.seed(seed)
    local_fake = Faker(["en_IN"])
    local_fake.seed_instance(seed)

    print(f"Generating synthetic dataset with seed={seed}...")
    
    # 1. Customers
    start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    customers = []
    customer_created_dates = {}
    for cid in range(1, num_customers + 1):
        name = local_fake.name()
        city = random.choice(INDIAN_CITIES)
        created_offset = random.randint(0, 365)  # Throughout 2023
        created_at = start_date + timedelta(days=created_offset, hours=random.randint(0, 23))
        customer_created_dates[cid] = created_at
        customers.append({
            "customer_id": cid,
            "customer_name": name,
            "city": city,
            "created_at": created_at.isoformat()
        })

    # 2. Stores & Products (Master static records)
    stores = [dict(s) for s in STORES_MASTER]
    products = [dict(p) for p in PRODUCTS_MASTER]
    # Active products that will receive orders (product_id 1 through 23)
    orderable_product_ids = [p["product_id"] for p in products if p["product_id"] <= 23]
    products_lookup = {p["product_id"]: p for p in products}

    # 3. Orders, Order Items, Payments
    orders = []
    order_items = []
    payments = []
    
    item_counter = 1
    payment_counter = 1
    
    # Customer ordering weights: 20% of customers are frequent shoppers (Power-law / Pareto)
    frequent_customers = list(range(1, int(num_customers * 0.2) + 1))
    regular_customers = list(range(int(num_customers * 0.2) + 1, num_customers + 1))
    
    for oid in range(1, num_orders + 1):
        # 60% probability order comes from top 20% customers
        if random.random() < 0.60:
            cid = random.choice(frequent_customers)
        else:
            cid = random.choice(regular_customers)
            
        store = random.choice(stores)
        cust_created = customer_created_dates[cid]
        
        # Order date happens AFTER customer account creation
        days_after_creation = random.randint(1, 300)
        order_date = cust_created + timedelta(
            days=days_after_creation,
            hours=random.randint(1, 12),
            minutes=random.randint(0, 59)
        )
        
        status = random.choices(ORDER_STATUSES, weights=STATUS_WEIGHTS)[0]
        
        orders.append({
            "order_id": oid,
            "customer_id": cid,
            "store_id": store["store_id"],
            "order_date": order_date.isoformat(),
            "status": status
        })
        
        # Generate 1 to 4 distinct items for this order
        num_items_in_order = random.choices([1, 2, 3, 4], weights=[0.55, 0.28, 0.12, 0.05])[0]
        chosen_pids = random.sample(orderable_product_ids, num_items_in_order)
        
        order_total = Decimal("0.00")
        
        for pid in chosen_pids:
            catalog_price = products_lookup[pid]["price"]
            # Preserving historical unit price: allows slight historical variance (e.g. promo discount)
            discount_factor = Decimal(str(random.choice([1.0, 1.0, 1.0, 0.95, 0.90])))
            unit_price = (catalog_price * discount_factor).quantize(Decimal("0.01"))
            quantity = random.choices([1, 2, 3, 5], weights=[0.70, 0.20, 0.08, 0.02])[0]
            
            line_total = unit_price * quantity
            order_total += line_total
            
            order_items.append({
                "item_id": item_counter,
                "order_id": oid,
                "product_id": pid,
                "quantity": quantity,
                "unit_price": str(unit_price)
            })
            item_counter += 1
            
        # Generate Payment record reflecting business rules
        payment_method = random.choices(PAYMENT_METHODS, weights=PAYMENT_METHOD_WEIGHTS)[0]
        
        if status == "Completed":
            payment_status = "Success"
            payment_amount = order_total
        elif status == "Pending":
            payment_status = random.choice(["Pending", "Failed"])
            payment_amount = order_total if payment_status == "Pending" else Decimal("0.00")
        else:  # Cancelled
            # In e-commerce, a cancelled order could be refunded if paid, or failed if rejected before payment
            payment_status = random.choice(["Refunded", "Failed"])
            payment_amount = order_total if payment_status == "Refunded" else Decimal("0.00")
            
        # INTENTIONAL ANOMALY for SQL Exercise 9 ("Orders with inconsistent payment records"):
        # We inject two deliberate inconsistencies out of 2200 orders:
        if oid == 100:
            # Anomaly 1: Completed order with a mismatched underpayment
            payment_amount = (order_total / Decimal("2")).quantize(Decimal("0.01"))
        elif oid == 250:
            # Anomaly 2: Completed order where payment status is stuck as 'Pending'
            payment_status = "Pending"
            
        payments.append({
            "payment_id": payment_counter,
            "order_id": oid,
            "amount": str(payment_amount),
            "payment_method": payment_method,
            "payment_status": payment_status
        })
        payment_counter += 1

    dataset = {
        "customers": customers,
        "products": [{**p, "price": str(p["price"])} for p in products],
        "stores": stores,
        "orders": orders,
        "order_items": order_items,
        "payments": payments
    }
    
    print(f"Generated: {len(customers)} customers, {len(products)} products, {len(stores)} stores, "
          f"{len(orders)} orders, {len(order_items)} items, {len(payments)} payments.")
    return dataset


def export_to_sql_seed(dataset: Dict[str, List[dict]], output_filepath: str):
    """
    Exports the generated dataset as an idempotent, executable SQL seed script.
    """
    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write("-- ==============================================================================\n")
        f.write("-- Agentic AI Data Analyst - Synthetic Data Seed Script\n")
        f.write(f"-- Generated with fixed random seed: {RANDOM_SEED}\n")
        f.write("-- ==============================================================================\n\n")
        f.write("BEGIN;\n\n")
        f.write("-- Clean existing rows in reverse dependency order\n")
        f.write("TRUNCATE TABLE payments, order_items, orders, stores, products, customers RESTART IDENTITY CASCADE;\n\n")
        
        # 1. Customers
        f.write("-- 1. Insert Customers\n")
        f.write("INSERT INTO customers (customer_id, customer_name, city, created_at) VALUES\n")
        cust_lines = []
        for c in dataset["customers"]:
            safe_name = c["customer_name"].replace("'", "''")
            cust_lines.append(f"({c['customer_id']}, '{safe_name}', '{c['city']}', '{c['created_at']}')")
        f.write(",\n".join(cust_lines) + ";\n\n")
        
        # 2. Products
        f.write("-- 2. Insert Products\n")
        f.write("INSERT INTO products (product_id, product_name, category, price) VALUES\n")
        prod_lines = []
        for p in dataset["products"]:
            safe_pname = p["product_name"].replace("'", "''")
            prod_lines.append(f"({p['product_id']}, '{safe_pname}', '{p['category']}', {p['price']})")
        f.write(",\n".join(prod_lines) + ";\n\n")
        
        # 3. Stores
        f.write("-- 3. Insert Stores\n")
        f.write("INSERT INTO stores (store_id, store_name, region) VALUES\n")
        store_lines = []
        for s in dataset["stores"]:
            safe_sname = s["store_name"].replace("'", "''")
            store_lines.append(f"({s['store_id']}, '{safe_sname}', '{s['region']}')")
        f.write(",\n".join(store_lines) + ";\n\n")
        
        # 4. Orders
        f.write("-- 4. Insert Orders\n")
        f.write("INSERT INTO orders (order_id, customer_id, store_id, order_date, status) VALUES\n")
        ord_lines = []
        for o in dataset["orders"]:
            ord_lines.append(f"({o['order_id']}, {o['customer_id']}, {o['store_id']}, '{o['order_date']}', '{o['status']}')")
        f.write(",\n".join(ord_lines) + ";\n\n")
        
        # 5. Order Items
        f.write("-- 5. Insert Order Items\n")
        f.write("INSERT INTO order_items (item_id, order_id, product_id, quantity, unit_price) VALUES\n")
        item_lines = []
        for item in dataset["order_items"]:
            item_lines.append(f"({item['item_id']}, {item['order_id']}, {item['product_id']}, {item['quantity']}, {item['unit_price']})")
        f.write(",\n".join(item_lines) + ";\n\n")
        
        # 6. Payments
        f.write("-- 6. Insert Payments\n")
        f.write("INSERT INTO payments (payment_id, order_id, amount, payment_method, payment_status) VALUES\n")
        pay_lines = []
        for pay in dataset["payments"]:
            pay_lines.append(f"({pay['payment_id']}, {pay['order_id']}, {pay['amount']}, '{pay['payment_method']}', '{pay['payment_status']}')")
        f.write(",\n".join(pay_lines) + ";\n\n")
        
        # Synchronize PostgreSQL sequences with maximum IDs
        f.write("-- Synchronize auto-increment sequences with loaded primary keys\n")
        f.write("SELECT setval('customers_customer_id_seq', (SELECT MAX(customer_id) FROM customers));\n")
        f.write("SELECT setval('products_product_id_seq', (SELECT MAX(product_id) FROM products));\n")
        f.write("SELECT setval('stores_store_id_seq', (SELECT MAX(store_id) FROM stores));\n")
        f.write("SELECT setval('orders_order_id_seq', (SELECT MAX(order_id) FROM orders));\n")
        f.write("SELECT setval('order_items_item_id_seq', (SELECT MAX(item_id) FROM order_items));\n")
        f.write("SELECT setval('payments_payment_id_seq', (SELECT MAX(payment_id) FROM payments));\n\n")
        
        f.write("COMMIT;\n")
        
    print(f"Exported SQL seed to: {output_filepath}")


if __name__ == "__main__":
    dataset = generate_synthetic_dataset(num_customers=500, num_orders=2200)
    seed_sql_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql", "seed.sql")
    export_to_sql_seed(dataset, seed_sql_path)
