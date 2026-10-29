-- ==============================================================================
-- Project: Agentic AI Data Analyst
-- Component: Phase 1 Business Analytical Queries & Exercises
-- Target Engine: PostgreSQL 14+ (also ANSI SQL compliant)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Exercise 1: Total Completed-Order Revenue
-- Business Definition: Total revenue is strictly the sum of (quantity * unit_price)
-- for all line items belonging to orders with status = 'Completed'.
-- Cancelled/Pending orders and refunded payments are excluded from recognized revenue.
-- ------------------------------------------------------------------------------
SELECT 
    SUM(oi.quantity * oi.unit_price) AS total_completed_revenue
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status = 'Completed';


-- ------------------------------------------------------------------------------
-- Exercise 2: Top Five Products by Revenue
-- Business Definition: Ranking products by gross completed revenue generated.
-- ------------------------------------------------------------------------------
SELECT 
    p.product_id,
    p.product_name,
    p.category,
    SUM(oi.quantity) AS total_units_sold,
    SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.status = 'Completed'
GROUP BY p.product_id, p.product_name, p.category
ORDER BY total_revenue DESC
LIMIT 5;


-- ------------------------------------------------------------------------------
-- Exercise 3: Monthly Revenue
-- Business Definition: Aggregating completed revenue chronologically by year & month
-- to analyze sales trends and growth patterns.
-- ------------------------------------------------------------------------------
SELECT 
    TO_CHAR(o.order_date, 'YYYY-MM') AS order_month,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(oi.quantity * oi.unit_price) AS monthly_revenue
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'Completed'
GROUP BY TO_CHAR(o.order_date, 'YYYY-MM')
ORDER BY order_month ASC;


-- ------------------------------------------------------------------------------
-- Exercise 4: Top Five Customers by Spending
-- Business Definition: Identifying high-value customers (whales/VIPs) for retention.
-- ------------------------------------------------------------------------------
SELECT 
    c.customer_id,
    c.customer_name,
    c.city,
    COUNT(DISTINCT o.order_id) AS completed_orders_count,
    SUM(oi.quantity * oi.unit_price) AS total_spend
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'Completed'
GROUP BY c.customer_id, c.customer_name, c.city
ORDER BY total_spend DESC
LIMIT 5;


-- ------------------------------------------------------------------------------
-- Exercise 5: Revenue by Store Region
-- Business Definition: Evaluating geographic sales distribution across store regions.
-- ------------------------------------------------------------------------------
SELECT 
    s.region,
    COUNT(DISTINCT s.store_id) AS store_count,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(oi.quantity * oi.unit_price) AS regional_revenue
FROM stores s
JOIN orders o ON s.store_id = o.store_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'Completed'
GROUP BY s.region
ORDER BY regional_revenue DESC;


-- ------------------------------------------------------------------------------
-- Exercise 6: Average Completed-Order Value (AOV)
-- Business Definition: Average Order Value (AOV) = Total Revenue / Total Orders.
-- Calculated both via CTE and aggregated order subquery.
-- ------------------------------------------------------------------------------
WITH order_totals AS (
    SELECT 
        o.order_id,
        SUM(oi.quantity * oi.unit_price) AS order_total
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.status = 'Completed'
    GROUP BY o.order_id
)
SELECT 
    COUNT(order_id) AS completed_orders,
    ROUND(AVG(order_total), 2) AS average_order_value,
    ROUND(MIN(order_total), 2) AS min_order_value,
    ROUND(MAX(order_total), 2) AS max_order_value
FROM order_totals;


-- ------------------------------------------------------------------------------
-- Exercise 7: Products Never Ordered
-- Business Definition: Identifies dead stock or unpurchased catalog items using
-- LEFT JOIN ... WHERE NULL.
-- ------------------------------------------------------------------------------
SELECT 
    p.product_id,
    p.product_name,
    p.category,
    p.price
FROM products p
LEFT JOIN order_items oi ON p.product_id = oi.product_id
WHERE oi.item_id IS NULL;


-- ------------------------------------------------------------------------------
-- Exercise 8: Customers with Multiple Orders
-- Business Definition: Customer repeat purchase rate & loyalty segmentation.
-- ------------------------------------------------------------------------------
SELECT 
    c.customer_id,
    c.customer_name,
    c.city,
    COUNT(o.order_id) AS total_orders_placed,
    COUNT(CASE WHEN o.status = 'Completed' THEN 1 END) AS completed_orders
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.customer_name, c.city
HAVING COUNT(o.order_id) > 1
ORDER BY total_orders_placed DESC;


-- ------------------------------------------------------------------------------
-- Exercise 9: Orders with Inconsistent Payment Records
-- Business Definition: Audit and reconciliation query detecting discrepancy
-- between calculated order total from items vs recorded payment amount or status.
-- ------------------------------------------------------------------------------
WITH order_item_aggregates AS (
    SELECT 
        order_id,
        ROUND(SUM(quantity * unit_price), 2) AS calculated_order_total
    FROM order_items
    GROUP BY order_id
)
SELECT 
    o.order_id,
    o.status AS order_status,
    oia.calculated_order_total,
    p.amount AS payment_amount,
    p.payment_status,
    p.payment_method,
    CASE 
        WHEN o.status = 'Completed' AND p.payment_status != 'Success' 
            THEN 'Status Mismatch: Order Completed but payment not Success'
        WHEN o.status = 'Completed' AND ROUND(p.amount, 2) != oia.calculated_order_total 
            THEN 'Amount Mismatch: Payment does not match items total'
        WHEN o.status = 'Cancelled' AND p.payment_status NOT IN ('Refunded', 'Failed') 
            THEN 'Cancelled order has unresolved payment status'
        ELSE 'Other Discrepancy'
    END AS anomaly_reason
FROM orders o
JOIN order_item_aggregates oia ON o.order_id = oia.order_id
JOIN payments p ON o.order_id = p.order_id
WHERE (o.status = 'Completed' AND (p.payment_status != 'Success' OR ROUND(p.amount, 2) != oia.calculated_order_total))
   OR (o.status = 'Cancelled' AND p.payment_status NOT IN ('Refunded', 'Failed'));


-- ------------------------------------------------------------------------------
-- Exercise 10: Sales by Product Category
-- Business Definition: Category contribution breakdown (Total revenue, units,
-- and percentage share of completed business revenue).
-- ------------------------------------------------------------------------------
WITH category_metrics AS (
    SELECT 
        p.category,
        COUNT(DISTINCT p.product_id) AS product_count,
        SUM(oi.quantity) AS units_sold,
        SUM(oi.quantity * oi.unit_price) AS category_revenue
    FROM products p
    JOIN order_items oi ON p.product_id = oi.product_id
    JOIN orders o ON oi.order_id = o.order_id
    WHERE o.status = 'Completed'
    GROUP BY p.category
)
SELECT 
    category,
    product_count,
    units_sold,
    category_revenue,
    ROUND(
        (category_revenue / SUM(category_revenue) OVER ()) * 100, 
        2
    ) AS revenue_percentage_share
FROM category_metrics
ORDER BY category_revenue DESC;
