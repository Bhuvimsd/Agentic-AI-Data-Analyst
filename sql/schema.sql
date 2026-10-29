-- ==============================================================================
-- Project: Agentic AI Data Analyst
-- Component: Phase 1 Relational Schema DDL
-- Target Engine: PostgreSQL 14+
-- Database: agentic_ai_analytics
-- ==============================================================================

-- Ensure clean, idempotent execution by dropping existing objects in reverse dependency order
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS stores CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- ------------------------------------------------------------------------------
-- 1. CUSTOMERS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for customer filtering by city and creation cohort
CREATE INDEX idx_customers_city ON customers(city);
CREATE INDEX idx_customers_created_at ON customers(created_at);

-- ------------------------------------------------------------------------------
-- 2. PRODUCTS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    category VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    CONSTRAINT chk_products_price_positive CHECK (price > 0)
);

-- Index for category-level aggregation and filtering
CREATE INDEX idx_products_category ON products(category);

-- ------------------------------------------------------------------------------
-- 3. STORES TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE stores (
    store_id SERIAL PRIMARY KEY,
    store_name VARCHAR(150) NOT NULL,
    region VARCHAR(50) NOT NULL,
    CONSTRAINT chk_stores_region CHECK (region IN ('North', 'South', 'East', 'West', 'Central'))
);

-- Index for regional grouping and filtering
CREATE INDEX idx_stores_region ON stores(region);

-- ------------------------------------------------------------------------------
-- 4. ORDERS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL,
    store_id INT NOT NULL,
    order_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) 
        REFERENCES customers(customer_id) ON DELETE RESTRICT,
    CONSTRAINT fk_orders_store FOREIGN KEY (store_id) 
        REFERENCES stores(store_id) ON DELETE RESTRICT,
    CONSTRAINT chk_orders_status CHECK (status IN ('Completed', 'Pending', 'Cancelled'))
);

-- Indexes for frequent operational joins and time-series aggregations
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_store_id ON orders(store_id);
CREATE INDEX idx_orders_order_date ON orders(order_date);
CREATE INDEX idx_orders_status ON orders(status);

-- ------------------------------------------------------------------------------
-- 5. ORDER_ITEMS TABLE (Preserves historical unit price at purchase time)
-- ------------------------------------------------------------------------------
CREATE TABLE order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) 
        REFERENCES orders(order_id) ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product FOREIGN KEY (product_id) 
        REFERENCES products(product_id) ON DELETE RESTRICT,
    CONSTRAINT chk_order_items_quantity_positive CHECK (quantity > 0),
    CONSTRAINT chk_order_items_unit_price_positive CHECK (unit_price > 0)
);

-- Indexes for order item lookups and product volume analytics
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);

-- ------------------------------------------------------------------------------
-- 6. PAYMENTS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE payments (
    payment_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    payment_status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_payments_order FOREIGN KEY (order_id) 
        REFERENCES orders(order_id) ON DELETE CASCADE,
    CONSTRAINT chk_payments_amount_non_negative CHECK (amount >= 0),
    CONSTRAINT chk_payments_method CHECK (payment_method IN ('UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Cash on Delivery')),
    CONSTRAINT chk_payments_status CHECK (payment_status IN ('Success', 'Pending', 'Failed', 'Refunded'))
);

-- Index for payment verification and order status reconciliation
CREATE INDEX idx_payments_order_id ON payments(order_id);
CREATE INDEX idx_payments_status ON payments(payment_status);
