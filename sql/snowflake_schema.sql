-- ==============================================================================
-- Project: Agentic AI Data Analyst
-- Component: Snowflake Data Cloud Schema DDL
-- Database: AGENTIC_AI_ANALYTICS
-- Schema: PUBLIC
-- ==============================================================================

-- 1. Create Database & Schema (if not exists)
CREATE DATABASE IF NOT EXISTS AGENTIC_AI_ANALYTICS;
USE DATABASE AGENTIC_AI_ANALYTICS;
CREATE SCHEMA IF NOT EXISTS PUBLIC;
USE SCHEMA PUBLIC;

-- 2. Clean existing tables (reverse dependency order)
DROP TABLE IF EXISTS PAYMENTS;
DROP TABLE IF EXISTS ORDER_ITEMS;
DROP TABLE IF EXISTS ORDERS;
DROP TABLE IF EXISTS STORES;
DROP TABLE IF EXISTS PRODUCTS;
DROP TABLE IF EXISTS CUSTOMERS;

-- ------------------------------------------------------------------------------
-- 1. CUSTOMERS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE CUSTOMERS (
    CUSTOMER_ID NUMBER(38, 0) AUTOINCREMENT PRIMARY KEY,
    CUSTOMER_NAME VARCHAR(150) NOT NULL,
    CITY VARCHAR(100) NOT NULL,
    CREATED_AT TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- ------------------------------------------------------------------------------
-- 2. PRODUCTS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE PRODUCTS (
    PRODUCT_ID NUMBER(38, 0) AUTOINCREMENT PRIMARY KEY,
    PRODUCT_NAME VARCHAR(200) NOT NULL,
    CATEGORY VARCHAR(100) NOT NULL,
    PRICE NUMBER(10, 2) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 3. STORES TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE STORES (
    STORE_ID NUMBER(38, 0) AUTOINCREMENT PRIMARY KEY,
    STORE_NAME VARCHAR(150) NOT NULL,
    REGION VARCHAR(50) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 4. ORDERS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE ORDERS (
    ORDER_ID NUMBER(38, 0) AUTOINCREMENT PRIMARY KEY,
    CUSTOMER_ID NUMBER(38, 0) NOT NULL,
    STORE_ID NUMBER(38, 0) NOT NULL,
    ORDER_DATE TIMESTAMP_NTZ NOT NULL,
    STATUS VARCHAR(50) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 5. ORDER_ITEMS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE ORDER_ITEMS (
    ITEM_ID NUMBER(38, 0) AUTOINCREMENT PRIMARY KEY,
    ORDER_ID NUMBER(38, 0) NOT NULL,
    PRODUCT_ID NUMBER(38, 0) NOT NULL,
    QUANTITY NUMBER(10, 0) NOT NULL,
    UNIT_PRICE NUMBER(10, 2) NOT NULL
);

-- ------------------------------------------------------------------------------
-- 6. PAYMENTS TABLE
-- ------------------------------------------------------------------------------
CREATE TABLE PAYMENTS (
    PAYMENT_ID NUMBER(38, 0) AUTOINCREMENT PRIMARY KEY,
    ORDER_ID NUMBER(38, 0) NOT NULL,
    PAYMENT_METHOD VARCHAR(50) NOT NULL,
    AMOUNT NUMBER(10, 2) NOT NULL,
    PAYMENT_STATUS VARCHAR(50) NOT NULL,
    PAYMENT_DATE TIMESTAMP_NTZ NOT NULL
);

-- ------------------------------------------------------------------------------
-- 7. LEAST-PRIVILEGE READ-ONLY ANALYST ROLE
-- ------------------------------------------------------------------------------
-- Run under ACCOUNTADMIN or SECURITYADMIN:
-- CREATE ROLE IF NOT EXISTS ANALYST_READONLY;
-- GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE ANALYST_READONLY;
-- GRANT USAGE ON DATABASE AGENTIC_AI_ANALYTICS TO ROLE ANALYST_READONLY;
-- GRANT USAGE ON SCHEMA AGENTIC_AI_ANALYTICS.PUBLIC TO ROLE ANALYST_READONLY;
-- GRANT SELECT ON ALL TABLES IN SCHEMA AGENTIC_AI_ANALYTICS.PUBLIC TO ROLE ANALYST_READONLY;
-- GRANT SELECT ON FUTURE TABLES IN SCHEMA AGENTIC_AI_ANALYTICS.PUBLIC TO ROLE ANALYST_READONLY;
