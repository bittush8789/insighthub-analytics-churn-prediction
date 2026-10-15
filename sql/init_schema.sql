-- E-commerce Customer Analytics & Churn Prediction Platform
-- Database Schema Initialization Script (PostgreSQL 14+)

-- Enable UUID extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Pipeline Runs (Metadata & Ingestion Audit)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    batch_id VARCHAR(64) PRIMARY KEY,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) NOT NULL,
    total_rows INTEGER DEFAULT 0,
    accepted_rows INTEGER DEFAULT 0,
    rejected_rows INTEGER DEFAULT 0,
    duplicate_rows INTEGER DEFAULT 0,
    missing_customer_rows INTEGER DEFAULT 0,
    cancellation_rows INTEGER DEFAULT 0,
    error_summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Data Quality Rejections Table
CREATE TABLE IF NOT EXISTS data_quality_rejections (
    id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(64) REFERENCES pipeline_runs(batch_id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    rejection_reason VARCHAR(255) NOT NULL,
    raw_record TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rejections_batch_id ON data_quality_rejections(batch_id);

-- 3. Customers Dimension Table
CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(64) PRIMARY KEY,
    country VARCHAR(100) NOT NULL DEFAULT 'Unknown',
    first_order_date TIMESTAMP WITH TIME ZONE,
    last_order_date TIMESTAMP WITH TIME ZONE,
    total_orders INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customers_country ON customers(country);

-- 4. Products Dimension Table
CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(64) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) DEFAULT 'General',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(product_name);

-- 5. Orders Table
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) REFERENCES customers(customer_id) ON DELETE SET NULL,
    order_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(32) NOT NULL,
    is_cancellation BOOLEAN NOT NULL DEFAULT FALSE,
    country VARCHAR(100) NOT NULL DEFAULT 'Unknown',
    gross_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    discount_or_return_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    net_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    batch_id VARCHAR(64) REFERENCES pipeline_runs(batch_id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_order_date ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_is_cancellation ON orders(is_cancellation);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_country ON orders(country);

-- 6. Order Items Table
CREATE TABLE IF NOT EXISTS order_items (
    item_id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 4) NOT NULL,
    line_total NUMERIC(14, 2) NOT NULL,
    line_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);

-- 7. Customer Features Table (Point-in-Time RFM & Behavioral Features)
CREATE TABLE IF NOT EXISTS customer_features (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    recency_days INTEGER NOT NULL,
    frequency INTEGER NOT NULL,
    monetary_value NUMERIC(14, 2) NOT NULL,
    average_order_value NUMERIC(14, 2) NOT NULL,
    purchase_interval_avg NUMERIC(10, 2) DEFAULT 0.00,
    purchase_interval_std NUMERIC(10, 2) DEFAULT 0.00,
    return_rate NUMERIC(6, 4) DEFAULT 0.0000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_snapshot UNIQUE (customer_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_customer_features_snapshot ON customer_features(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_customer_features_customer ON customer_features(customer_id);

-- 8. Churn Predictions Table
CREATE TABLE IF NOT EXISTS churn_predictions (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    prediction_date DATE NOT NULL,
    churn_probability NUMERIC(6, 4) NOT NULL,
    risk_segment VARCHAR(32) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    model_type VARCHAR(64) NOT NULL,
    threshold_applied NUMERIC(6, 4) NOT NULL DEFAULT 0.5000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_prediction UNIQUE (customer_id, prediction_date, model_version)
);

CREATE INDEX IF NOT EXISTS idx_churn_predictions_risk ON churn_predictions(risk_segment);
CREATE INDEX IF NOT EXISTS idx_churn_predictions_prob ON churn_predictions(churn_probability);
CREATE INDEX IF NOT EXISTS idx_churn_predictions_date ON churn_predictions(prediction_date);
