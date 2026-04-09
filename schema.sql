-- ============================================================
-- StudentShelf Database Schema
-- Normalized to Third Normal Form (3NF)
-- Final version
-- ============================================================

CREATE DATABASE IF NOT EXISTS studentshelf_db;
USE studentshelf_db;

-- ============================================================
-- TABLE 1: categories
-- ============================================================
CREATE TABLE IF NOT EXISTS categories (
    category_id   INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE
);

INSERT INTO categories (category_name) VALUES
    ('Textbook'),
    ('Lab Equipment'),
    ('Calculator'),
    ('Stationery'),
    ('Electronics'),
    ('Other');

-- ============================================================
-- TABLE 2: users
-- phone added for contact sharing between buyer and seller
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id     INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100)  NOT NULL,
    email       VARCHAR(150)  NOT NULL UNIQUE,
    password    VARCHAR(255)  NOT NULL,
    phone       VARCHAR(15)   DEFAULT NULL,
    trust_score INT           DEFAULT 0,
    created_at  TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE 3: products
-- stock = how many units the seller has available
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    product_id  INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT             NOT NULL,
    category_id INT             NOT NULL,
    name        VARCHAR(200)    NOT NULL,
    description TEXT,
    price       DECIMAL(10, 2)  NOT NULL,
    stock       INT             NOT NULL DEFAULT 1,
    status      ENUM('Available', 'Sold') DEFAULT 'Available',
    listed_at   TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_product_seller
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
        ON DELETE RESTRICT
);

-- ============================================================
-- TABLE 4: transactions
-- buyer_id is NULL when seller marks sold without a specific buyer
-- ============================================================
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    buyer_id       INT       NULL,
    product_id     INT       NOT NULL,
    date           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_transaction_buyer
        FOREIGN KEY (buyer_id) REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transaction_product
        FOREIGN KEY (product_id) REFERENCES products(product_id)
        ON DELETE CASCADE
);

-- ============================================================
-- TABLE 5: requests
-- Tracks buyer interest in a product
-- Status flow: Pending → Ongoing → Completed
--                      → Rejected
-- Phone numbers of both parties revealed only at Ongoing stage
-- ============================================================
CREATE TABLE IF NOT EXISTS requests (
    request_id   INT AUTO_INCREMENT PRIMARY KEY,
    product_id   INT NOT NULL,
    buyer_id     INT NOT NULL,
    status       ENUM('Pending','Accepted','Ongoing','Rejected','Completed')
                 DEFAULT 'Pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- A buyer can only send ONE request per product
    UNIQUE KEY unique_request (product_id, buyer_id),

    CONSTRAINT fk_request_product
        FOREIGN KEY (product_id) REFERENCES products(product_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_request_buyer
        FOREIGN KEY (buyer_id) REFERENCES users(user_id)
        ON DELETE CASCADE
);