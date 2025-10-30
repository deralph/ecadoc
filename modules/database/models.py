"""
Database models and operations for the Floor Plan Agent API
"""
import os
import re
import sqlite3
import mysql.connector
from mysql.connector import Error as MySQLError
import psycopg2
from psycopg2 import Error as PostgreSQLError
from psycopg2.extras import RealDictCursor
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timezone
from modules.config.settings import settings

@dataclass
class User:
    """User data model"""
    id: Optional[int] = None
    firstname: str = ""
    lastname: str = ""
    email: str = ""
    password: str = ""
    google_id: Optional[str] = None
    is_verified: bool = False
    verification_token: Optional[str] = None
    verification_token_expires: Optional[datetime] = None
    created_at: Optional[datetime] = None

@dataclass
class EmailVerificationToken:
    """Email verification token data model"""
    id: Optional[int] = None
    user_id: int = 0
    token: str = ""
    expires_at: datetime = None
    created_at: Optional[datetime] = None
    used_at: Optional[datetime] = None

@dataclass
class Document:
    """Document data model"""
    id: Optional[int] = None
    doc_id: str = ""  # Unique document identifier (UUID)
    filename: str = ""
    file_id: str = ""  # Reference to file_storage table
    pages: int = 0
    chunks_indexed: int = 0
    status: str = "active"  # active, file_missing, error
    user_id: int = 0  # Owner of the document
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate document data"""
        if not self.doc_id or not self.filename:
            return False
        if not self.file_id:  # file_id is required for database storage
            return False
        if self.pages < 0 or self.chunks_indexed < 0:
            return False
        if self.status not in ['active', 'file_missing', 'error', 'processing']:
            return False
        if self.user_id <= 0:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'doc_id': self.doc_id,
            'filename': self.filename,
            'file_id': self.file_id,
            'pages': self.pages,
            'chunks_indexed': self.chunks_indexed,
            'status': self.status,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

@dataclass
class Project:
    """Project data model"""
    id: Optional[int] = None
    project_id: str = ""  # Unique project identifier
    name: str = ""
    description: str = ""
    user_id: int = 0
    doc_ids: Optional[List[str]] = None  # Associated document IDs as list
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ProjectShare:
    """Project sharing invitation"""
    id: Optional[int] = None
    project_id: str = ""
    inviter_user_id: int = 0
    invitee_user_id: int = 0
    status: str = "pending"  # pending, accepted, rejected
    invitation_token: Optional[str] = None
    created_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None


@dataclass
class SubscriptionPlan:
    """Subscription plan definition"""
    id: Optional[int] = None
    plan_code: str = ""
    name: str = ""
    interval_months: int = 0
    amount_cents: int = 0
    stripe_price_id: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class UserSubscription:
    """Active subscription for a user"""
    id: Optional[int] = None
    user_id: int = 0
    plan_code: str = ""
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    status: str = "inactive"
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    cancellation_effective_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class UserProfilePhoto:
    """Stored reference to a user's profile photo"""
    id: Optional[int] = None
    user_id: int = 0
    object_key: str = ""
    url: Optional[str] = None
    storage_backend: str = "s3"
    etag: Optional[str] = None
    last_updated: Optional[datetime] = None


@dataclass
class ChatSession:
    """Enhanced chat session data model with context support"""
    id: Optional[int] = None
    session_id: str = ""
    user_id: int = 0
    context_type: str = ""  # PROJECT, DOCUMENT, GENERAL
    context_id: Optional[str] = None  # project_id, doc_id, or None for general
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None  # Additional context data

@dataclass
class ChatMessage:
    """Enhanced chat message data model with context support"""
    id: Optional[int] = None
    user_id: int = 0
    session_id: str = ""
    role: str = ""  # 'user' or 'assistant'
    message: str = ""
    timestamp: Optional[datetime] = None
    context_type: Optional[str] = None  # PROJECT, DOCUMENT, GENERAL
    context_id: Optional[str] = None  # project_id, doc_id, or None for general

@dataclass
class FileStorage:
    """File storage data model for binary file storage in database"""
    id: Optional[int] = None
    file_id: str = ""
    filename: str = ""
    content_type: str = ""
    file_size: int = 0
    file_data: bytes = b""
    user_id: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate file storage data"""
        if not self.file_id or not self.filename:
            return False
        if not self.content_type or not isinstance(self.file_data, bytes):
            return False
        if self.file_size != len(self.file_data):
            return False
        if self.user_id <= 0:
            return False
        return True
    
    def to_dict(self, include_data: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding binary data"""
        result = {
            'id': self.id,
            'file_id': self.file_id,
            'filename': self.filename,
            'content_type': self.content_type,
            'file_size': self.file_size,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        if include_data:
            result['file_data'] = self.file_data
        return result

@dataclass
class VectorChunk:
    """Vector chunk data model for pgvector storage"""
    id: Optional[int] = None
    chunk_id: str = ""
    doc_id: str = ""
    page_number: int = 0
    chunk_text: str = ""
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate vector chunk data"""
        if not self.chunk_id or not self.doc_id:
            return False
        if not self.chunk_text.strip():
            return False
        if self.page_number < 1:
            return False
        if self.embedding and len(self.embedding) != 1536:  # OpenAI embedding dimension
            return False
        return True
    
    def to_dict(self, include_embedding: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding embedding vector"""
        result = {
            'id': self.id,
            'chunk_id': self.chunk_id,
            'doc_id': self.doc_id,
            'page_number': self.page_number,
            'chunk_text': self.chunk_text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_embedding and self.embedding:
            result['embedding'] = self.embedding
        return result

@dataclass
class GeneratedOutput:
    """Generated output data model for storing processed files"""
    id: Optional[int] = None
    output_id: str = ""
    filename: str = ""
    content_type: str = ""
    file_size: int = 0
    file_data: bytes = b""
    source_doc_id: Optional[str] = None
    user_id: int = 0
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate generated output data"""
        if not self.output_id or not self.filename:
            return False
        if not self.content_type or not isinstance(self.file_data, bytes):
            return False
        if self.file_size != len(self.file_data):
            return False
        if self.user_id <= 0:
            return False
        return True
    
    def to_dict(self, include_data: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding binary data"""
        result = {
            'id': self.id,
            'output_id': self.output_id,
            'filename': self.filename,
            'content_type': self.content_type,
            'file_size': self.file_size,
            'source_doc_id': self.source_doc_id,
            'user_id': self.user_id,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_data:
            result['file_data'] = self.file_data
        return result

class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self, db_name: str = None):
        self.db_name = db_name or settings.DATABASE_NAME
        self.use_rds = settings.USE_RDS
        
        # Determine database type based on port
        self.is_postgres = settings.DB_PORT == 5432
        
        if self.use_rds:
            if self.is_postgres:
                self.postgres_config = {
                    'host': settings.DB_HOST,
                    'port': settings.DB_PORT,
                    'database': settings.DB_NAME,
                    'user': settings.DB_USER,
                    'password': settings.DB_PASSWORD,
                    'connect_timeout': 30
                }
            else:
                self.mysql_config = {
                    'host': settings.DB_HOST,
                    'port': settings.DB_PORT,
                    'database': settings.DB_NAME,
                    'user': settings.DB_USER,
                    'password': settings.DB_PASSWORD,
                    'autocommit': False,
                    'charset': 'utf8mb4',
                    'collation': 'utf8mb4_unicode_ci',
                    # Connection pooling and timeout settings
                    'pool_name': 'esticore_pool',
                    'pool_size': 10,
                    'pool_reset_session': True,
                    'connect_timeout': 30,
                    'sql_mode': 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'
                }
        
        self.init_database()
    
    def get_connection(self):
        """Get database connection with retry logic and proper error handling"""
        if self.use_rds:
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    if self.is_postgres:
                        return psycopg2.connect(**self.postgres_config)
                    else:
                        return mysql.connector.connect(**self.mysql_config)
                except (PostgreSQLError, MySQLError) as e:
                    if attempt == max_retries - 1:
                        db_type = "PostgreSQL" if self.is_postgres else "MySQL"
                        raise Exception(f"Failed to connect to {db_type} after {max_retries} attempts: {e}")
                    
                    # Handle specific connection errors
                    import time
                    print(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                except Exception as e:
                    raise Exception(f"Unexpected database connection error: {e}")
        else:
            return sqlite3.connect(self.db_name)
    
    def execute_with_retry(self, query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
        """Execute query with connection retry logic and proper error handling"""
        max_retries = 3
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()
                if self.is_postgres:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                else:
                    cur = conn.cursor()
                
                if params:
                    cur.execute(query, params)
                else:
                    cur.execute(query)
                
                if fetch_one:
                    result = cur.fetchone()
                elif fetch_all:
                    result = cur.fetchall()
                else:
                    result = cur.rowcount
                
                conn.commit()
                return result
                
            except (PostgreSQLError, MySQLError) as e:
                if conn:
                    conn.rollback()
                
                # Handle specific database errors that might be retryable
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))  # Progressive delay
                    continue
                else:
                    db_type = "PostgreSQL" if self.is_postgres else "MySQL"
                    raise Exception(f"{db_type} query error: {e}")
            except Exception as e:
                if conn:
                    conn.rollback()
                raise Exception(f"Database query error: {e}")
            finally:
                if conn:
                    conn.close()
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        if self.use_rds and self.is_postgres:
            # PostgreSQL table creation statements
            print("Initializing PostgreSQL database...")
            
            # Ensure pgvector extension is available
            self.ensure_pgvector_extension()
            
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS userdata(
                    id SERIAL PRIMARY KEY,
                    firstname VARCHAR(255) NOT NULL,
                    lastname VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    google_id VARCHAR(255) UNIQUE,
                    is_verified BOOLEAN DEFAULT FALSE,
                    verification_token VARCHAR(255),
                    verification_token_expires TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create chat history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chathistory(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    context_type VARCHAR(20) CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                    context_id VARCHAR(255),
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for chathistory
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chathistory_context ON chathistory (context_type, context_id)")
            
            # Create projects table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects(
                    id SERIAL PRIMARY KEY,
                    project_id VARCHAR(255) UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    user_id INTEGER NOT NULL,
                    doc_ids TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            
            # Create documents table (updated schema)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id SERIAL PRIMARY KEY,
                    doc_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    file_id VARCHAR(255),
                    pages INTEGER DEFAULT 0,
                    chunks_indexed INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'active',
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for documents
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status)")
            
            # Create project_documents junction table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_documents(
                    id SERIAL PRIMARY KEY,
                    project_id VARCHAR(255) NOT NULL,
                    doc_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
                    UNIQUE (project_id, doc_id)
                )
            """)

            # Create indexes for project_documents
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_project_id ON project_documents (project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_doc_id ON project_documents (doc_id)")

            # Create project_shares table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_shares(
                    id SERIAL PRIMARY KEY,
                    project_id VARCHAR(255) NOT NULL,
                    inviter_user_id INTEGER NOT NULL,
                    invitee_user_id INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    invitation_token VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    responded_at TIMESTAMP NULL,
                    UNIQUE(project_id, invitee_user_id),
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (inviter_user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    FOREIGN KEY (invitee_user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_shares_invitee ON project_shares (invitee_user_id, status)")

            # Create subscription tables
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscription_plans(
                    id SERIAL PRIMARY KEY,
                    plan_code VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    interval_months INTEGER NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    stripe_price_id VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    plan_code VARCHAR(50) NOT NULL,
                    stripe_subscription_id VARCHAR(255),
                    stripe_customer_id VARCHAR(255),
                    status VARCHAR(30) NOT NULL DEFAULT 'inactive',
                    current_period_start TIMESTAMP NULL,
                    current_period_end TIMESTAMP NULL,
                    cancel_at_period_end BOOLEAN DEFAULT FALSE,
                    cancellation_effective_date TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id),
                    FOREIGN KEY (plan_code) REFERENCES subscription_plans (plan_code),
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscription_events(
                    id SERIAL PRIMARY KEY,
                    event_type VARCHAR(100) NOT NULL,
                    stripe_event_id VARCHAR(255),
                    payload JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_subscription_events_type ON subscription_events (event_type)")

            # Create user profile photo table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_profile_photos(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    object_key VARCHAR(500) NOT NULL,
                    url VARCHAR(500),
                    storage_backend VARCHAR(50) NOT NULL,
                    etag VARCHAR(255),
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)

            # Create chat_sessions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions(
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    context_type VARCHAR(20) NOT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                    context_id VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for chat_sessions
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_context ON chat_sessions (user_id, context_type, context_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id ON chat_sessions (session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_activity ON chat_sessions (last_activity)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_active ON chat_sessions (user_id, is_active)")

            conn.commit()

            # Create new tables for file and vector storage
            self.create_new_tables()
            
            # Migrate documents table if needed
            self.migrate_documents_table()
            
            # Create test user if not exists
            cur.execute("SELECT * FROM userdata WHERE email = %s", ("test@example.com",))
            if not cur.fetchone():
                test_password = hashlib.sha256("testuser1".encode()).hexdigest()
                cur.execute(
                    "INSERT INTO userdata (firstname, lastname, email, password) VALUES (%s, %s, %s, %s)",
                    ("Test", "User", "test@example.com", test_password)
                )
                
        elif self.use_rds:
            # MySQL table creation statements
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS userdata(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    firstname VARCHAR(255) NOT NULL,
                    lastname VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    google_id VARCHAR(255) UNIQUE,
                    is_verified BOOLEAN DEFAULT FALSE,
                    verification_token VARCHAR(255),
                    verification_token_expires TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create chat history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chathistory(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    session_id TEXT NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NULL,
                    context_id VARCHAR(255) NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    INDEX idx_context (context_type, context_id)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create projects table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    project_id VARCHAR(255) UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    user_id INT NOT NULL,
                    doc_ids TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create documents table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    doc_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    pdf_path TEXT NOT NULL,
                    vector_path TEXT,
                    pages INT DEFAULT 0,
                    chunks_indexed INT DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'active',
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    INDEX idx_doc_id (doc_id),
                    INDEX idx_user_id (user_id),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create project_documents junction table for many-to-many relationship
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_documents(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    project_id VARCHAR(255) NOT NULL,
                    doc_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
                    UNIQUE KEY unique_project_document (project_id, doc_id),
                    INDEX idx_project_id (project_id),
                    INDEX idx_doc_id (doc_id)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create chat_sessions table for enhanced session management
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    user_id INT NOT NULL,
                    context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NOT NULL,
                    context_id VARCHAR(255) NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    metadata JSON NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE,
                    INDEX idx_user_context (user_id, context_type, context_id),
                    INDEX idx_session_id (session_id),
                    INDEX idx_last_activity (last_activity),
                    INDEX idx_active_sessions (user_id, is_active)
                ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create test user if not exists
            cur.execute("SELECT * FROM userdata WHERE email = %s", ("test@example.com",))
            if not cur.fetchone():
                test_password = hashlib.sha256("testuser1".encode()).hexdigest()
                cur.execute(
                    "INSERT INTO userdata (firstname, lastname, email, password) VALUES (%s, %s, %s, %s)",
                    ("Test", "User", "test@example.com", test_password)
                )
        else:
            # SQLite table creation statements (legacy)
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS userdata(
                    id INTEGER PRIMARY KEY,
                    firstname VARCHAR(255) NOT NULL,
                    lastname VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    google_id VARCHAR(255) UNIQUE,
                    is_verified BOOLEAN DEFAULT 0,
                    verification_token VARCHAR(255),
                    verification_token_expires DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create chat history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chathistory(
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    context_type TEXT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL') OR context_type IS NULL),
                    context_id TEXT NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata (id)
                )
            """)
            
            # Create indexes for chathistory table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chathistory_context ON chathistory (context_type, context_id)")
            
            # Create projects table (handle migration from doc_id to doc_ids)
            # First check if projects table exists and what columns it has
            cur.execute("PRAGMA table_info(projects)")
            columns = [row[1] for row in cur.fetchall()]
            
            if not columns:  # Table doesn't exist, create new one
                cur.execute("""
                    CREATE TABLE projects(
                        id INTEGER PRIMARY KEY,
                        project_id TEXT UNIQUE NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT,
                        user_id INTEGER NOT NULL,
                        doc_ids TEXT,  -- Store multiple document IDs as JSON array
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES userdata (id)
                    )
                """)
            elif 'doc_id' in columns and 'doc_ids' not in columns:
                # Migrate from old schema (doc_id) to new schema (doc_ids)
                self._migrate_projects_schema(cur)
            elif 'doc_ids' not in columns:
                # Add doc_ids column if it doesn't exist
                cur.execute("ALTER TABLE projects ADD COLUMN doc_ids TEXT")
            
            # Create documents table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id INTEGER PRIMARY KEY,
                    doc_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    pdf_path TEXT NOT NULL,
                    vector_path TEXT NOT NULL,
                    pages INTEGER DEFAULT 0,
                    chunks_indexed INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    user_id INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id)
                )
            """)
            
            # Create indexes for documents table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status)")
            
            # Create project_documents junction table for many-to-many relationship
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_documents(
                    id INTEGER PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
                    UNIQUE (project_id, doc_id)
                )
            """)
            
            # Create indexes for project_documents table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_project_id ON project_documents (project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_doc_id ON project_documents (doc_id)")

            # Create project_shares table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_shares(
                    id INTEGER PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    inviter_user_id INTEGER NOT NULL,
                    invitee_user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    invitation_token TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    responded_at DATETIME,
                    UNIQUE(project_id, invitee_user_id),
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    FOREIGN KEY (inviter_user_id) REFERENCES userdata (id) ON DELETE CASCADE,
                    FOREIGN KEY (invitee_user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_project_shares_invitee ON project_shares (invitee_user_id, status)")

            # Create subscription tables
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscription_plans(
                    id INTEGER PRIMARY KEY,
                    plan_code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    interval_months INTEGER NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    stripe_price_id TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions(
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    plan_code TEXT NOT NULL,
                    stripe_subscription_id TEXT,
                    stripe_customer_id TEXT,
                    status TEXT NOT NULL DEFAULT 'inactive',
                    current_period_start DATETIME,
                    current_period_end DATETIME,
                    cancel_at_period_end BOOLEAN DEFAULT 0,
                    cancellation_effective_date DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_code) REFERENCES subscription_plans (plan_code),
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS subscription_events(
                    id INTEGER PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    stripe_event_id TEXT,
                    payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_subscription_events_type ON subscription_events (event_type)")

            # Create user profile photo table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_profile_photos(
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    object_key TEXT NOT NULL,
                    url TEXT,
                    storage_backend TEXT NOT NULL,
                    etag TEXT,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
            """)

            # Create chat_sessions table for enhanced session management
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions(
                    id INTEGER PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    context_type TEXT NOT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                    context_id TEXT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for chat_sessions table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_context ON chat_sessions (user_id, context_type, context_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id ON chat_sessions (session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_last_activity ON chat_sessions (last_activity)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_active ON chat_sessions (user_id, is_active)")
            
            # Create test user if not exists
            cur.execute("SELECT * FROM userdata WHERE email = ?", ("test@example.com",))
            if not cur.fetchone():
                test_password = hashlib.sha256("testuser1".encode()).hexdigest()
                cur.execute(
                    "INSERT INTO userdata (firstname, lastname, email, password) VALUES (?, ?, ?, ?)",
                    ("Test", "User", "test@example.com", test_password)
                )
        
        # Ensure subscription plans exist after schema setup
        try:
            self.ensure_default_subscription_plans()
        except Exception as seed_error:
            print(f"WARNING: Failed to seed subscription plans: {seed_error}")

        conn.commit()
        conn.close()
        
        # Run migration for existing databases
        self._migrate_documents_schema()
        self._migrate_email_verification_schema()
        self._migrate_session_schema()
    
    def _migrate_documents_schema(self):
        """Migrate documents table to include vector_path column if it doesn't exist"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            if self.use_rds:
                # Check if documents table exists first
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_SCHEMA = %s 
                    AND TABLE_NAME = 'documents'
                """, (settings.DB_NAME,))
                
                table_exists = cur.fetchone()[0] > 0
                
                if table_exists:
                    # Check if vector_path column exists in MySQL
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'documents' 
                        AND COLUMN_NAME = 'vector_path'
                    """, (settings.DB_NAME,))
                    
                    column_exists = cur.fetchone()[0] > 0
                    
                    if not column_exists:
                        print("Adding vector_path column to documents table (MySQL)...")
                        # MySQL TEXT columns cannot have default values
                        cur.execute("ALTER TABLE documents ADD COLUMN vector_path TEXT")
                        
                        # Update existing records with vector paths
                        cur.execute("SELECT doc_id FROM documents WHERE vector_path IS NULL")
                        docs_to_update = cur.fetchall()
                        
                        for (doc_id,) in docs_to_update:
                            vector_path = os.path.join(settings.VECTORS_DIR, doc_id)
                            cur.execute("UPDATE documents SET vector_path = %s WHERE doc_id = %s", (vector_path, doc_id))
                        
                        conn.commit()
                        print(f"Updated {len(docs_to_update)} documents with vector paths")
                    else:
                        print("vector_path column already exists in documents table")
            else:
                # Check if documents table exists first for SQLite
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
                table_exists = cur.fetchone() is not None
                
                if table_exists:
                    # Check if vector_path column exists in SQLite
                    cur.execute("PRAGMA table_info(documents)")
                    columns = [row[1] for row in cur.fetchall()]
                    
                    if 'vector_path' not in columns:
                        print("Adding vector_path column to documents table (SQLite)...")
                        cur.execute("ALTER TABLE documents ADD COLUMN vector_path TEXT NOT NULL DEFAULT ''")
                        
                        # Update existing records with vector paths
                        cur.execute("SELECT doc_id FROM documents WHERE vector_path = '' OR vector_path IS NULL")
                        docs_to_update = cur.fetchall()
                        
                        for (doc_id,) in docs_to_update:
                            vector_path = os.path.join(settings.VECTORS_DIR, doc_id)
                            cur.execute("UPDATE documents SET vector_path = ? WHERE doc_id = ?", (vector_path, doc_id))
                        
                        conn.commit()
                        print(f"Updated {len(docs_to_update)} documents with vector paths")
                    else:
                        print("vector_path column already exists in documents table")
                        
        except Exception as e:
            print(f"Migration error: {e}")
            if conn:
                conn.rollback()
            # Don't raise the exception to prevent breaking initialization
        finally:
            if conn:
                conn.close()
    
    def _get_placeholder(self):
        """Get the appropriate parameter placeholder for the database type"""
        if self.use_rds:
            return "%s" if not self.is_postgres else "%s"
        return "?"

    def _to_datetime(self, value: Any) -> Optional[datetime]:
        """Best-effort conversion to datetime"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.utcfromtimestamp(value)
            except Exception:
                return None
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
                try:
                    dt = datetime.strptime(value, fmt)
                    if not dt.tzinfo:
                        return dt
                    return dt.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    continue
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except Exception:
                return None
        return None

    def _row_get(self, row: Any, key: str, index: int):
        """Compatibility helper for dictionary/tuple rows"""
        if isinstance(row, dict):
            return row.get(key)
        return row[index]

    def _format_datetime(self, value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        return value

    def ensure_pgvector_extension(self) -> bool:
        """Ensure pgvector extension is available in PostgreSQL"""
        if not self.is_postgres:
            return True  # Not needed for non-PostgreSQL databases
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Try to create the extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
            
            # Verify the extension is available
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            result = cur.fetchone()
            
            if result:
                print("pgvector extension is available")
                return True
            else:
                print("WARNING: pgvector extension could not be created")
                return False
                
        except Exception as e:
            print(f"Error setting up pgvector extension: {e}")
            print("Please install pgvector extension manually:")
            print("1. Connect to your PostgreSQL database as superuser")
            print("2. Run: CREATE EXTENSION vector;")
            return False
        finally:
            if conn:
                conn.close()
    
    def create_new_tables(self):
        """Create new tables for file storage and vector operations"""
        if not self.is_postgres:
            print("New table creation is only supported for PostgreSQL")
            return
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Create file_storage table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS file_storage (
                    id SERIAL PRIMARY KEY,
                    file_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100) NOT NULL,
                    file_size BIGINT NOT NULL,
                    file_data BYTEA NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for file_storage
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_storage_file_id ON file_storage (file_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_storage_user_id ON file_storage (user_id)")
            
            # Create vector_chunks table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vector_chunks (
                    id SERIAL PRIMARY KEY,
                    chunk_id VARCHAR(255) UNIQUE NOT NULL,
                    doc_id VARCHAR(255) NOT NULL,
                    page_number INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding vector(1536),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for vector_chunks
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vector_chunks_doc_id ON vector_chunks (doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_vector_chunks_page_number ON vector_chunks (page_number)")
            
            # Create vector similarity index (only if pgvector is available)
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_vector_chunks_embedding ON vector_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
            except Exception as e:
                print(f"Could not create vector index (pgvector may not be available): {e}")
            
            # Create generated_outputs table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS generated_outputs (
                    id SERIAL PRIMARY KEY,
                    output_id VARCHAR(255) UNIQUE NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    content_type VARCHAR(100) NOT NULL,
                    file_size BIGINT NOT NULL,
                    file_data BYTEA NOT NULL,
                    source_doc_id VARCHAR(255),
                    user_id INTEGER NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_doc_id) REFERENCES documents(doc_id) ON DELETE SET NULL,
                    FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for generated_outputs
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generated_outputs_output_id ON generated_outputs (output_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generated_outputs_source_doc_id ON generated_outputs (source_doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generated_outputs_user_id ON generated_outputs (user_id)")
            
            conn.commit()
            print("Successfully created new tables for file and vector storage")
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error creating new tables: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def migrate_documents_table(self):
        """Migrate documents table to remove file paths and add file_id"""
        if not self.is_postgres:
            print("Documents table migration is only supported for PostgreSQL")
            return
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Check if file_id column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'documents' AND column_name = 'file_id'
            """)
            
            if not cur.fetchone():
                # Add file_id column
                cur.execute("ALTER TABLE documents ADD COLUMN file_id VARCHAR(255)")
                
                # Add foreign key constraint
                cur.execute("""
                    ALTER TABLE documents 
                    ADD CONSTRAINT fk_documents_file_id 
                    FOREIGN KEY (file_id) REFERENCES file_storage(file_id) ON DELETE SET NULL
                """)
                
                print("Added file_id column to documents table")
            
            # Check if old columns exist and remove them
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'documents' AND column_name IN ('pdf_path', 'vector_path')
            """)
            
            old_columns = cur.fetchall()
            for column in old_columns:
                column_name = column[0] if isinstance(column, tuple) else column['column_name']
                cur.execute(f"ALTER TABLE documents DROP COLUMN IF EXISTS {column_name}")
                print(f"Removed {column_name} column from documents table")
            
            conn.commit()
            print("Successfully migrated documents table")
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error migrating documents table: {e}")
            # Don't raise exception to prevent breaking initialization
        finally:
            if conn:
                conn.close()
    
    # File storage operations
    def store_file(self, file_id: str, filename: str, content_type: str, file_data: bytes, user_id: int) -> bool:
        """Store file as binary data in database"""
        if not self.is_postgres:
            raise Exception("File storage is only supported with PostgreSQL")
        
        # Validate input parameters
        if not file_id or not filename or not content_type:
            raise ValueError("file_id, filename, and content_type are required")
        if not isinstance(file_data, bytes):
            raise ValueError("file_data must be bytes")
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO file_storage (file_id, filename, content_type, file_size, file_data, user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (file_id, filename, content_type, len(file_data), file_data, user_id))
            
            conn.commit()
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error storing file: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_file(self, file_id: str) -> Optional[FileStorage]:
        """Retrieve file from database"""
        if not self.is_postgres:
            raise Exception("File storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                SELECT id, file_id, filename, content_type, file_size, file_data, user_id, created_at, updated_at
                FROM file_storage WHERE file_id = %s
            """, (file_id,))
            
            row = cur.fetchone()
            if row:
                # Convert memoryview to bytes if needed
                file_data = row['file_data']
                if isinstance(file_data, memoryview):
                    file_data = file_data.tobytes()
                
                return FileStorage(
                    id=row['id'],
                    file_id=row['file_id'],
                    filename=row['filename'],
                    content_type=row['content_type'],
                    file_size=row['file_size'],
                    file_data=file_data,
                    user_id=row['user_id'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
            return None
            
        except Exception as e:
            raise Exception(f"Error retrieving file: {e}")
        finally:
            if conn:
                conn.close()
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file from database"""
        if not self.is_postgres:
            raise Exception("File storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("DELETE FROM file_storage WHERE file_id = %s", (file_id,))
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error deleting file: {e}")
        finally:
            if conn:
                conn.close()
    
    # Vector storage operations
    def store_vector_chunks(self, doc_id: str, chunks: List[Dict[str, Any]]) -> int:
        """Store vector chunks for a document"""
        if not self.is_postgres:
            raise Exception("Vector storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            stored_count = 0
            for chunk in chunks:
                chunk_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO vector_chunks (chunk_id, doc_id, page_number, chunk_text, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    chunk_id,
                    doc_id,
                    chunk.get('page', 1),
                    chunk.get('text', ''),
                    chunk.get('embedding')
                ))
                stored_count += 1
            
            conn.commit()
            return stored_count
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error storing vector chunks: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_vector_chunks(self, doc_id: str) -> List[VectorChunk]:
        """Get all vector chunks for a document"""
        if not self.is_postgres:
            raise Exception("Vector storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                SELECT id, chunk_id, doc_id, page_number, chunk_text, embedding, created_at
                FROM vector_chunks WHERE doc_id = %s ORDER BY page_number, id
            """, (doc_id,))
            
            chunks = []
            for row in cur.fetchall():
                chunks.append(VectorChunk(
                    id=row['id'],
                    chunk_id=row['chunk_id'],
                    doc_id=row['doc_id'],
                    page_number=row['page_number'],
                    chunk_text=row['chunk_text'],
                    embedding=row['embedding'],
                    created_at=row['created_at']
                ))
            
            return chunks
            
        except Exception as e:
            raise Exception(f"Error retrieving vector chunks: {e}")
        finally:
            if conn:
                conn.close()
    
    def similarity_search(self, doc_id: str, query_embedding: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """Perform similarity search using pgvector"""
        if not self.is_postgres:
            raise Exception("Vector similarity search is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Convert embedding to string format for PostgreSQL
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
            
            cur.execute("""
                SELECT chunk_id, doc_id, page_number, chunk_text, 
                       embedding <=> %s::vector as distance
                FROM vector_chunks 
                WHERE doc_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (embedding_str, doc_id, embedding_str, k))
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'chunk_id': row['chunk_id'],
                    'doc_id': row['doc_id'],
                    'page': row['page_number'],
                    'text': row['chunk_text'],
                    'distance': float(row['distance']),
                    'similarity_score': 1 - float(row['distance'])  # Convert distance to similarity
                })
            
            return results
            
        except Exception as e:
            raise Exception(f"Error performing similarity search: {e}")
        finally:
            if conn:
                conn.close()
    
    def delete_vector_chunks(self, doc_id: str) -> bool:
        """Delete all vector chunks for a document"""
        if not self.is_postgres:
            raise Exception("Vector storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("DELETE FROM vector_chunks WHERE doc_id = %s", (doc_id,))
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error deleting vector chunks: {e}")
        finally:
            if conn:
                conn.close()
    
    # Generated output operations
    def store_generated_output(self, output_id: str, filename: str, content_type: str, 
                              file_data: bytes, source_doc_id: str, user_id: int, 
                              metadata: Dict[str, Any] = None) -> bool:
        """Store generated output file"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO generated_outputs (output_id, filename, content_type, file_size, 
                                             file_data, source_doc_id, user_id, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (output_id, filename, content_type, len(file_data), file_data, 
                  source_doc_id, user_id, json.dumps(metadata) if metadata else None))
            
            conn.commit()
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error storing generated output: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_generated_output(self, output_id: str) -> Optional[GeneratedOutput]:
        """Retrieve generated output from database"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            cur.execute("""
                SELECT id, output_id, filename, content_type, file_size, file_data, 
                       source_doc_id, user_id, metadata, created_at
                FROM generated_outputs WHERE output_id = %s
            """, (output_id,))
            
            row = cur.fetchone()
            if row:
                # Convert memoryview to bytes if needed
                file_data = row['file_data']
                if isinstance(file_data, memoryview):
                    file_data = file_data.tobytes()
                
                return GeneratedOutput(
                    id=row['id'],
                    output_id=row['output_id'],
                    filename=row['filename'],
                    content_type=row['content_type'],
                    file_size=row['file_size'],
                    file_data=file_data,
                    source_doc_id=row['source_doc_id'],
                    user_id=row['user_id'],
                    metadata=row['metadata'] if row['metadata'] else None,  # JSONB is already parsed
                    created_at=row['created_at']
                )
            return None
            
        except Exception as e:
            raise Exception(f"Error retrieving generated output: {e}")
        finally:
            if conn:
                conn.close()
    
    def list_generated_outputs(self, user_id: int = None) -> List[GeneratedOutput]:
        """List generated outputs, optionally filtered by user"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            if user_id:
                cur.execute("""
                    SELECT id, output_id, filename, content_type, file_size, 
                           source_doc_id, user_id, metadata, created_at
                    FROM generated_outputs WHERE user_id = %s ORDER BY created_at DESC
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT id, output_id, filename, content_type, file_size, 
                           source_doc_id, user_id, metadata, created_at
                    FROM generated_outputs ORDER BY created_at DESC
                """)
            
            outputs = []
            for row in cur.fetchall():
                outputs.append(GeneratedOutput(
                    id=row['id'],
                    output_id=row['output_id'],
                    filename=row['filename'],
                    content_type=row['content_type'],
                    file_size=row['file_size'],
                    file_data=b"",  # Don't load file data for listing
                    source_doc_id=row['source_doc_id'],
                    user_id=row['user_id'],
                    metadata=row['metadata'] if row['metadata'] else None,  # JSONB is already parsed
                    created_at=row['created_at']
                ))
            
            return outputs
            
        except Exception as e:
            raise Exception(f"Error listing generated outputs: {e}")
        finally:
            if conn:
                conn.close()
    
    def delete_generated_output(self, output_id: str) -> bool:
        """Delete generated output from database"""
        if not self.is_postgres:
            raise Exception("Generated output storage is only supported with PostgreSQL")
        
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("DELETE FROM generated_outputs WHERE output_id = %s", (output_id,))
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error deleting generated output: {e}")
        finally:
            if conn:
                conn.close()
    
    def _migrate_projects_schema(self, cur):
        """Migrate projects table from doc_id to doc_ids schema"""
        # Create new table with updated schema
        cur.execute("""
            CREATE TABLE projects_new(
                id INTEGER PRIMARY KEY,
                project_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                user_id INTEGER NOT NULL,
                doc_ids TEXT,  -- Store multiple document IDs as JSON array
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES userdata (id)
            )
        """)
        
        # Migrate data from old table to new table
        cur.execute("""
            INSERT INTO projects_new (id, project_id, name, description, user_id, doc_ids, created_at, updated_at)
            SELECT id, project_id, name, description, user_id, 
                   CASE 
                       WHEN doc_id IS NOT NULL THEN '["' || doc_id || '"]'
                       ELSE NULL
                   END as doc_ids,
                   created_at, updated_at
            FROM projects
        """)
        
        # Drop old table and rename new one
        cur.execute("DROP TABLE projects")
        cur.execute("ALTER TABLE projects_new RENAME TO projects")
    
    def create_user(self, firstname: str, lastname: str, email: str, password: str, google_id: str = None) -> int:
        """Create a new user"""
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO userdata (firstname, lastname, email, password, google_id) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (firstname, lastname, email, hashed_password, google_id)
            )
            conn.commit()
            
            # Get the new user's ID
            cur.execute(f"SELECT id FROM userdata WHERE email = {placeholder}", (email,))
            user = cur.fetchone()
            return user[0] if user else None
            
        finally:
            conn.close()
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE email = {placeholder}",
                (email,)
            )
            row = cur.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    is_verified=bool(row[6]) if row[6] is not None else False,
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
                )
            return None
            
        finally:
            conn.close()
    
    def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Get user by Google ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE google_id = {placeholder}",
                (google_id,)
            )
            row = cur.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    is_verified=bool(row[6]) if row[6] is not None else False,
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
                )
            return None
            
        finally:
            conn.close()
    
    def verify_user_credentials(self, email: str, password: str) -> Optional[User]:
        """Verify user credentials"""
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE email = {placeholder} AND password = {placeholder}",
                (email, hashed_password)
            )
            row = cur.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    is_verified=bool(row[6]) if row[6] is not None else False,
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
                )
            return None
            
        finally:
            conn.close()
    
    def update_user_google_id(self, user_id: int, google_id: str):
        """Update user's Google ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"UPDATE userdata SET google_id = {placeholder} WHERE id = {placeholder}", (google_id, user_id))
            conn.commit()
        finally:
            conn.close()
    
    def add_chat_message(self, user_id: int, session_id: str, role: str, message: str, context_type: str = None, context_id: str = None):
        """Add a chat message to history with optional context information"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                INSERT INTO chathistory (user_id, session_id, role, message, context_type, context_id) 
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (user_id, session_id, role, message, context_type, context_id))
            
            conn.commit()
            
            # Update session activity if session exists
            self.update_session_activity(session_id)
        finally:
            conn.close()
    
    def get_chat_history(self, user_id: int, session_id: str = None, limit: int = 50) -> List[ChatMessage]:
        """Get chat history for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if session_id:
                if self.use_rds:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
                        FROM chathistory 
                        WHERE user_id = %s AND session_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (user_id, session_id, limit))
                else:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
                        FROM chathistory 
                        WHERE user_id = ? AND session_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (user_id, session_id, limit))
            else:
                if self.use_rds:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
                        FROM chathistory 
                        WHERE user_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (user_id, limit))
                else:
                    cur.execute("""
                        SELECT id, user_id, session_id, role, message, timestamp, context_type, context_id
                        FROM chathistory 
                        WHERE user_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (user_id, limit))
            
            rows = cur.fetchall()
            return [
                ChatMessage(
                    id=row[0],
                    user_id=row[1],
                    session_id=row[2],
                    role=row[3],
                    message=row[4],
                    timestamp=row[5],
                    context_type=row[6],
                    context_id=row[7]
                )
                for row in rows
            ]
            
        finally:
            conn.close()
    
    def get_user_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all unique session IDs for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT DISTINCT session_id, MAX(timestamp) as last_activity
                FROM chathistory 
                WHERE user_id = {placeholder}
                GROUP BY session_id
                ORDER BY last_activity DESC
            """, (user_id,))
            
            sessions = cur.fetchall()
            return [
                {
                    "session_id": session[0],
                    "last_activity": session[1]
                }
                for session in sessions
            ]
            
        finally:
            conn.close()
    
    def get_project_session(self, user_id: int, project_id: str) -> Optional[str]:
        """Get the most recent session ID associated with a specific project for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Search for chat messages that mention the project ID
            # This looks for messages that contain the project ID in the content
            cur.execute(f"""
                SELECT session_id, MAX(timestamp) as last_activity
                FROM chathistory 
                WHERE user_id = {placeholder} 
                AND (message LIKE {placeholder} OR message LIKE {placeholder})
                GROUP BY session_id
                ORDER BY last_activity DESC
                LIMIT 1
            """, (user_id, f"%Project ID: {project_id}%", f"%project_id%{project_id}%"))
            
            row = cur.fetchone()
            return row[0] if row else None
            
        except Exception as e:
            # If there's an error, return None to fall back to creating a new session
            return None
        finally:
            conn.close()
    
    # Enhanced session management methods
    def create_chat_session(self, session_id: str, user_id: int, context_type: str, context_id: str = None, metadata: Dict[str, Any] = None) -> bool:
        """Create a new chat session with context support"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            metadata_json = json.dumps(metadata) if metadata else None
            
            cur.execute(f"""
                INSERT INTO chat_sessions (session_id, user_id, context_type, context_id, metadata)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (session_id, user_id, context_type, context_id, metadata_json))
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error creating chat session: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_session_by_id(self, session_id: str) -> Optional[ChatSession]:
        """Get session by session ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT id, session_id, user_id, context_type, context_id, is_active, 
                       created_at, last_activity, metadata
                FROM chat_sessions 
                WHERE session_id = {placeholder}
            """, (session_id,))
            
            row = cur.fetchone()
            if row:
                metadata = json.loads(row[8]) if row[8] else None
                return ChatSession(
                    id=row[0],
                    session_id=row[1],
                    user_id=row[2],
                    context_type=row[3],
                    context_id=row[4],
                    is_active=bool(row[5]),
                    created_at=row[6],
                    last_activity=row[7],
                    metadata=metadata
                )
            return None
        finally:
            conn.close()
    
    def get_session_by_context(self, user_id: int, context_type: str, context_id: str = None) -> Optional[ChatSession]:
        """Get the most recent active session for a specific context"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if context_id is None:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder} AND context_type = {placeholder} AND context_id IS NULL
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                    LIMIT 1
                """, (user_id, context_type))
            else:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder} AND context_type = {placeholder} AND context_id = {placeholder}
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                    LIMIT 1
                """, (user_id, context_type, context_id))
            
            row = cur.fetchone()
            if row:
                metadata = json.loads(row[8]) if row[8] else None
                return ChatSession(
                    id=row[0],
                    session_id=row[1],
                    user_id=row[2],
                    context_type=row[3],
                    context_id=row[4],
                    is_active=bool(row[5]),
                    created_at=row[6],
                    last_activity=row[7],
                    metadata=metadata
                )
            return None
        finally:
            conn.close()
    
    def get_active_sessions(self, user_id: int, context_type: str = None) -> List[ChatSession]:
        """Get all active sessions for a user, optionally filtered by context type"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if context_type:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder} AND context_type = {placeholder}
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                """, (user_id, context_type))
            else:
                cur.execute(f"""
                    SELECT id, session_id, user_id, context_type, context_id, is_active, 
                           created_at, last_activity, metadata
                    FROM chat_sessions 
                    WHERE user_id = {placeholder}
                    AND is_active = {'TRUE' if self.use_rds else '1'}
                    ORDER BY last_activity DESC
                """, (user_id,))
            
            rows = cur.fetchall()
            sessions = []
            for row in rows:
                metadata = json.loads(row[8]) if row[8] else None
                sessions.append(ChatSession(
                    id=row[0],
                    session_id=row[1],
                    user_id=row[2],
                    context_type=row[3],
                    context_id=row[4],
                    is_active=bool(row[5]),
                    created_at=row[6],
                    last_activity=row[7],
                    metadata=metadata
                ))
            return sessions
        finally:
            conn.close()
    
    def update_session_activity(self, session_id: str) -> bool:
        """Update the last activity timestamp for a session"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                # MySQL automatically updates last_activity with ON UPDATE CURRENT_TIMESTAMP
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET last_activity = CURRENT_TIMESTAMP 
                    WHERE session_id = {placeholder}
                """, (session_id,))
            else:
                # SQLite needs manual timestamp update
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET last_activity = CURRENT_TIMESTAMP 
                    WHERE session_id = {placeholder}
                """, (session_id,))
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error updating session activity: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def deactivate_session(self, session_id: str) -> bool:
        """Mark a session as inactive"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                UPDATE chat_sessions 
                SET is_active = {'FALSE' if self.use_rds else '0'}
                WHERE session_id = {placeholder}
            """, (session_id,))
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error deactivating session: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def cleanup_expired_sessions(self, hours: int = 24) -> int:
        """Mark sessions as inactive if they haven't been active for the specified hours"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET is_active = FALSE
                    WHERE is_active = TRUE 
                    AND last_activity < NOW() - INTERVAL '{placeholder} hours'
                """, (hours,))
            else:
                cur.execute(f"""
                    UPDATE chat_sessions 
                    SET is_active = 0
                    WHERE is_active = 1 
                    AND datetime(last_activity, '+{placeholder} hours') < datetime('now')
                """, (hours,))
            
            conn.commit()
            cleaned_count = cur.rowcount
            print(f"Cleaned up {cleaned_count} expired sessions")
            return cleaned_count
        except Exception as e:
            print(f"Error cleaning up expired sessions: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()
    
    def add_chat_message_with_context(self, user_id: int, session_id: str, role: str, message: str, context_type: str = None, context_id: str = None):
        """Add a chat message to history with context information"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                INSERT INTO chathistory (user_id, session_id, role, message, context_type, context_id) 
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (user_id, session_id, role, message, context_type, context_id))
            
            conn.commit()
            
            # Update session activity
            self.update_session_activity(session_id)
        finally:
            conn.close()
    
    # Project management methods
    def create_project(self, project_id: str, name: str, description: str, user_id: int, doc_ids: Optional[List[str]] = None) -> int:
        """Create a new project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Convert doc_ids list to JSON string if present
            doc_ids_str = None
            if doc_ids and len(doc_ids) > 0:
                doc_ids_str = json.dumps(doc_ids)
            
            cur.execute(
                f"INSERT INTO projects (project_id, name, description, user_id, doc_ids) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                (project_id, name, description, user_id, doc_ids_str)
            )
            conn.commit()
            
            # Get the new project's ID
            cur.execute(f"SELECT id FROM projects WHERE project_id = {placeholder}", (project_id,))
            project = cur.fetchone()
            return project[0] if project else None
            
        finally:
            conn.close()
    
    def update_project_document(self, project_id: str, doc_ids: List[str]) -> bool:
        """Update the document IDs for a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            # Convert doc_ids list to JSON string
            doc_ids_str = json.dumps(doc_ids)
            
            cur.execute(
                f"UPDATE projects SET doc_ids = {placeholder} WHERE project_id = {placeholder}",
                (doc_ids_str, project_id)
            )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def get_project_by_id(self, project_id: str) -> Optional[Project]:
        """Get project by project ID"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT id, project_id, name, description, user_id, doc_ids, created_at, updated_at 
                FROM projects 
                WHERE project_id = {placeholder}
            """, (project_id,))
            row = cur.fetchone()
            
            if row:
                # Parse doc_ids from JSON string if present
                doc_ids = None
                if row[5]:
                    try:
                        doc_ids = json.loads(row[5])
                    except json.JSONDecodeError:
                        doc_ids = [row[5]]  # Fallback to old single doc_id format
                
                return Project(
                    id=row[0],
                    project_id=row[1],
                    name=row[2],
                    description=row[3],
                    user_id=row[4],
                    doc_ids=doc_ids,
                    created_at=row[6],
                    updated_at=row[7]
                )
            return None
            
        finally:
            conn.close()
    
    def get_user_projects(self, user_id: int) -> List[Project]:
        """Get all projects for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, project_id, name, description, user_id, doc_ids, created_at, updated_at FROM projects WHERE user_id = {placeholder} ORDER BY created_at DESC",
                (user_id,)
            )
            rows = cur.fetchall()
            
            result = []
            for row in rows:
                # Parse doc_ids from JSON string if present
                doc_ids = None
                if row[5]:
                    try:
                        doc_ids = json.loads(row[5])
                    except json.JSONDecodeError:
                        doc_ids = [row[5]]  # Fallback to old single doc_id format
                
                result.append(Project(
                    id=row[0],
                    project_id=row[1],
                    name=row[2],
                    description=row[3],
                    user_id=row[4],
                    doc_ids=doc_ids,
                    created_at=row[6],
                    updated_at=row[7]
                ))
            
            return result

        finally:
            conn.close()

    def get_project_share(self, project_id: str, invitee_user_id: int) -> Optional[ProjectShare]:
        """Retrieve a project share invitation"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, project_id, inviter_user_id, invitee_user_id, status, invitation_token, created_at, responded_at "
                f"FROM project_shares WHERE project_id = {placeholder} AND invitee_user_id = {placeholder}",
                (project_id, invitee_user_id),
            )
            row = cur.fetchone()
            if not row:
                return None

            return ProjectShare(
                id=self._row_get(row, 'id', 0),
                project_id=self._row_get(row, 'project_id', 1),
                inviter_user_id=self._row_get(row, 'inviter_user_id', 2),
                invitee_user_id=self._row_get(row, 'invitee_user_id', 3),
                status=self._row_get(row, 'status', 4),
                invitation_token=self._row_get(row, 'invitation_token', 5),
                created_at=self._to_datetime(self._row_get(row, 'created_at', 6)),
                responded_at=self._to_datetime(self._row_get(row, 'responded_at', 7)),
            )
        finally:
            conn.close()

    def create_or_update_project_share(
        self,
        project_id: str,
        inviter_user_id: int,
        invitee_user_id: int,
        status: str = 'pending',
        invitation_token: str = None,
    ) -> ProjectShare:
        """Create a new share or update an existing pending invite"""
        existing = self.get_project_share(project_id, invitee_user_id)
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            if existing:
                cur.execute(
                    f"""
                        UPDATE project_shares
                        SET inviter_user_id = {placeholder},
                            status = {placeholder},
                            invitation_token = {placeholder},
                            created_at = CURRENT_TIMESTAMP,
                            responded_at = NULL
                        WHERE project_id = {placeholder} AND invitee_user_id = {placeholder}
                    """,
                    (inviter_user_id, status, invitation_token, project_id, invitee_user_id),
                )
            else:
                cur.execute(
                    f"INSERT INTO project_shares (project_id, inviter_user_id, invitee_user_id, status, invitation_token)"
                    f" VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (project_id, inviter_user_id, invitee_user_id, status, invitation_token),
                )
            conn.commit()
        finally:
            conn.close()

        return self.get_project_share(project_id, invitee_user_id)

    def update_project_share_status(
        self,
        project_id: str,
        invitee_user_id: int,
        status: str,
    ) -> Optional[ProjectShare]:
        """Update a share status and set responded_at"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"""
                    UPDATE project_shares
                    SET status = {placeholder},
                        responded_at = CURRENT_TIMESTAMP
                    WHERE project_id = {placeholder} AND invitee_user_id = {placeholder}
                """,
                (status, project_id, invitee_user_id),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_project_share(project_id, invitee_user_id)

    def list_shared_projects_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        """List projects shared with a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"""
                    SELECT ps.id, ps.project_id, ps.inviter_user_id, ps.invitee_user_id, ps.status, ps.invitation_token,
                           ps.created_at, ps.responded_at,
                           p.name, p.description, p.user_id AS owner_user_id, p.created_at AS project_created_at,
                           p.updated_at AS project_updated_at
                    FROM project_shares ps
                    INNER JOIN projects p ON p.project_id = ps.project_id
                    WHERE ps.invitee_user_id = {placeholder}
                    ORDER BY ps.created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    "share_id": self._row_get(row, 'id', 0),
                    "project_id": self._row_get(row, 'project_id', 1),
                    "inviter_user_id": self._row_get(row, 'inviter_user_id', 2),
                    "invitee_user_id": self._row_get(row, 'invitee_user_id', 3),
                    "status": self._row_get(row, 'status', 4),
                    "invitation_token": self._row_get(row, 'invitation_token', 5),
                    "created_at": self._to_datetime(self._row_get(row, 'created_at', 6)),
                    "responded_at": self._to_datetime(self._row_get(row, 'responded_at', 7)),
                    "project": {
                        "name": self._row_get(row, 'name', 8),
                        "description": self._row_get(row, 'description', 9),
                        "owner_user_id": self._row_get(row, 'owner_user_id', 10),
                        "created_at": self._to_datetime(self._row_get(row, 'project_created_at', 11)),
                        "updated_at": self._to_datetime(self._row_get(row, 'project_updated_at', 12)),
                    },
                })
            return result
        finally:
            conn.close()

    def user_has_project_access(self, project_id: str, user_id: int) -> bool:
        """Check if user is owner or accepted share"""
        # Ownership check
        project = self.get_project_by_id(project_id)
        if project and project.user_id == user_id:
            return True

        share = self.get_project_share(project_id, user_id)
        return bool(share and share.status == 'accepted')

    # Subscription management
    def upsert_subscription_plan(
        self,
        plan_code: str,
        name: str,
        interval_months: int,
        amount_cents: int,
        stripe_price_id: str = None,
        is_active: bool = True,
    ) -> SubscriptionPlan:
        """Create or update a subscription plan"""
        conn = self.get_connection()
        cur = conn.cursor()

        params = (plan_code, name, interval_months, amount_cents, stripe_price_id, is_active)

        try:
            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        """
                            INSERT INTO subscription_plans (plan_code, name, interval_months, amount_cents, stripe_price_id, is_active)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (plan_code) DO UPDATE SET
                                name = EXCLUDED.name,
                                interval_months = EXCLUDED.interval_months,
                                amount_cents = EXCLUDED.amount_cents,
                                stripe_price_id = EXCLUDED.stripe_price_id,
                                is_active = EXCLUDED.is_active,
                                updated_at = CURRENT_TIMESTAMP
                        """,
                        params,
                    )
                else:
                    cur.execute(
                        """
                            INSERT INTO subscription_plans (plan_code, name, interval_months, amount_cents, stripe_price_id, is_active)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                name = VALUES(name),
                                interval_months = VALUES(interval_months),
                                amount_cents = VALUES(amount_cents),
                                stripe_price_id = VALUES(stripe_price_id),
                                is_active = VALUES(is_active),
                                updated_at = CURRENT_TIMESTAMP
                        """,
                        params,
                    )
            else:
                cur.execute(
                    """
                        INSERT INTO subscription_plans (plan_code, name, interval_months, amount_cents, stripe_price_id, is_active)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(plan_code) DO UPDATE SET
                            name = excluded.name,
                            interval_months = excluded.interval_months,
                            amount_cents = excluded.amount_cents,
                            stripe_price_id = excluded.stripe_price_id,
                            is_active = excluded.is_active,
                            updated_at = CURRENT_TIMESTAMP
                    """,
                    (plan_code, name, interval_months, amount_cents, stripe_price_id, int(is_active)),
                )
            conn.commit()
        finally:
            conn.close()

        return self.get_subscription_plan(plan_code)

    def get_subscription_plan(self, plan_code: str) -> Optional[SubscriptionPlan]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, plan_code, name, interval_months, amount_cents, stripe_price_id, is_active, created_at, updated_at "
                f"FROM subscription_plans WHERE plan_code = {placeholder}",
                (plan_code,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return SubscriptionPlan(
                id=self._row_get(row, 'id', 0),
                plan_code=self._row_get(row, 'plan_code', 1),
                name=self._row_get(row, 'name', 2),
                interval_months=self._row_get(row, 'interval_months', 3),
                amount_cents=self._row_get(row, 'amount_cents', 4),
                stripe_price_id=self._row_get(row, 'stripe_price_id', 5),
                is_active=bool(self._row_get(row, 'is_active', 6)),
                created_at=self._to_datetime(self._row_get(row, 'created_at', 7)),
                updated_at=self._to_datetime(self._row_get(row, 'updated_at', 8)),
            )
        finally:
            conn.close()

    def get_active_subscription_plans(self) -> List[SubscriptionPlan]:
        conn = self.get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                "SELECT id, plan_code, name, interval_months, amount_cents, stripe_price_id, is_active, created_at, updated_at "
                "FROM subscription_plans WHERE is_active = 1 OR is_active = TRUE ORDER BY interval_months"
            )
            rows = cur.fetchall()
            plans = []
            for row in rows:
                plans.append(
                    SubscriptionPlan(
                        id=self._row_get(row, 'id', 0),
                        plan_code=self._row_get(row, 'plan_code', 1),
                        name=self._row_get(row, 'name', 2),
                        interval_months=self._row_get(row, 'interval_months', 3),
                        amount_cents=self._row_get(row, 'amount_cents', 4),
                        stripe_price_id=self._row_get(row, 'stripe_price_id', 5),
                        is_active=bool(self._row_get(row, 'is_active', 6)),
                        created_at=self._to_datetime(self._row_get(row, 'created_at', 7)),
                        updated_at=self._to_datetime(self._row_get(row, 'updated_at', 8)),
                    )
                )
            return plans
        finally:
            conn.close()

    def create_or_update_user_subscription(
        self,
        user_id: int,
        plan_code: str,
        stripe_subscription_id: str,
        stripe_customer_id: str,
        status: str,
        current_period_start: datetime = None,
        current_period_end: datetime = None,
        cancel_at_period_end: bool = False,
        cancellation_effective_date: datetime = None,
    ) -> UserSubscription:
        conn = self.get_connection()
        cur = conn.cursor()

        params = (
            user_id,
            plan_code,
            stripe_subscription_id,
            stripe_customer_id,
            status,
            self._format_datetime(current_period_start),
            self._format_datetime(current_period_end),
            cancel_at_period_end,
            self._format_datetime(cancellation_effective_date),
        )

        try:
            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        """
                            INSERT INTO user_subscriptions (user_id, plan_code, stripe_subscription_id, stripe_customer_id, status,
                                current_period_start, current_period_end, cancel_at_period_end, cancellation_effective_date)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (user_id) DO UPDATE SET
                                plan_code = EXCLUDED.plan_code,
                                stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                                stripe_customer_id = EXCLUDED.stripe_customer_id,
                                status = EXCLUDED.status,
                                current_period_start = EXCLUDED.current_period_start,
                                current_period_end = EXCLUDED.current_period_end,
                                cancel_at_period_end = EXCLUDED.cancel_at_period_end,
                                cancellation_effective_date = EXCLUDED.cancellation_effective_date,
                                updated_at = CURRENT_TIMESTAMP
                        """,
                        params,
                    )
                else:
                    cur.execute(
                        """
                            INSERT INTO user_subscriptions (user_id, plan_code, stripe_subscription_id, stripe_customer_id, status,
                                current_period_start, current_period_end, cancel_at_period_end, cancellation_effective_date)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                plan_code = VALUES(plan_code),
                                stripe_subscription_id = VALUES(stripe_subscription_id),
                                stripe_customer_id = VALUES(stripe_customer_id),
                                status = VALUES(status),
                                current_period_start = VALUES(current_period_start),
                                current_period_end = VALUES(current_period_end),
                                cancel_at_period_end = VALUES(cancel_at_period_end),
                                cancellation_effective_date = VALUES(cancellation_effective_date),
                                updated_at = CURRENT_TIMESTAMP
                        """,
                        params,
                    )
            else:
                cur.execute(
                    """
                        INSERT INTO user_subscriptions (user_id, plan_code, stripe_subscription_id, stripe_customer_id, status,
                            current_period_start, current_period_end, cancel_at_period_end, cancellation_effective_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            plan_code = excluded.plan_code,
                            stripe_subscription_id = excluded.stripe_subscription_id,
                            stripe_customer_id = excluded.stripe_customer_id,
                            status = excluded.status,
                            current_period_start = excluded.current_period_start,
                            current_period_end = excluded.current_period_end,
                            cancel_at_period_end = excluded.cancel_at_period_end,
                            cancellation_effective_date = excluded.cancellation_effective_date,
                            updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        user_id,
                        plan_code,
                        stripe_subscription_id,
                        stripe_customer_id,
                        status,
                        self._format_datetime(current_period_start),
                        self._format_datetime(current_period_end),
                        int(cancel_at_period_end),
                        self._format_datetime(cancellation_effective_date),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        return self.get_user_subscription_by_user(user_id)

    def update_subscription_status(
        self,
        stripe_subscription_id: str,
        status: str,
        current_period_start: datetime = None,
        current_period_end: datetime = None,
        cancel_at_period_end: bool = None,
        cancellation_effective_date: datetime = None,
    ) -> Optional[UserSubscription]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        updates = ["status = {placeholder}".format(placeholder=placeholder)]
        params: List[Any] = [status]

        if current_period_start is not None:
            updates.append(f"current_period_start = {placeholder}")
            params.append(self._format_datetime(current_period_start))
        if current_period_end is not None:
            updates.append(f"current_period_end = {placeholder}")
            params.append(self._format_datetime(current_period_end))
        if cancel_at_period_end is not None:
            updates.append(f"cancel_at_period_end = {placeholder}")
            params.append(cancel_at_period_end if self.use_rds else int(cancel_at_period_end))
        if cancellation_effective_date is not None:
            updates.append(f"cancellation_effective_date = {placeholder}")
            params.append(self._format_datetime(cancellation_effective_date))

        updates.append("updated_at = CURRENT_TIMESTAMP")

        set_clause = ", ".join(updates)

        params.append(stripe_subscription_id)

        try:
            cur.execute(
                f"UPDATE user_subscriptions SET {set_clause} WHERE stripe_subscription_id = {placeholder}",
                tuple(params),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_subscription_by_stripe_id(stripe_subscription_id)

    def get_user_subscription_by_user(self, user_id: int) -> Optional[UserSubscription]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, user_id, plan_code, stripe_subscription_id, stripe_customer_id, status, current_period_start, "
                f"current_period_end, cancel_at_period_end, cancellation_effective_date, created_at, updated_at "
                f"FROM user_subscriptions WHERE user_id = {placeholder}",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return UserSubscription(
                id=self._row_get(row, 'id', 0),
                user_id=self._row_get(row, 'user_id', 1),
                plan_code=self._row_get(row, 'plan_code', 2),
                stripe_subscription_id=self._row_get(row, 'stripe_subscription_id', 3),
                stripe_customer_id=self._row_get(row, 'stripe_customer_id', 4),
                status=self._row_get(row, 'status', 5),
                current_period_start=self._to_datetime(self._row_get(row, 'current_period_start', 6)),
                current_period_end=self._to_datetime(self._row_get(row, 'current_period_end', 7)),
                cancel_at_period_end=bool(self._row_get(row, 'cancel_at_period_end', 8)),
                cancellation_effective_date=self._to_datetime(self._row_get(row, 'cancellation_effective_date', 9)),
                created_at=self._to_datetime(self._row_get(row, 'created_at', 10)),
                updated_at=self._to_datetime(self._row_get(row, 'updated_at', 11)),
            )
        finally:
            conn.close()

    def get_subscription_by_stripe_id(self, stripe_subscription_id: str) -> Optional[UserSubscription]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, user_id, plan_code, stripe_subscription_id, stripe_customer_id, status, current_period_start, "
                f"current_period_end, cancel_at_period_end, cancellation_effective_date, created_at, updated_at "
                f"FROM user_subscriptions WHERE stripe_subscription_id = {placeholder}",
                (stripe_subscription_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return UserSubscription(
                id=self._row_get(row, 'id', 0),
                user_id=self._row_get(row, 'user_id', 1),
                plan_code=self._row_get(row, 'plan_code', 2),
                stripe_subscription_id=self._row_get(row, 'stripe_subscription_id', 3),
                stripe_customer_id=self._row_get(row, 'stripe_customer_id', 4),
                status=self._row_get(row, 'status', 5),
                current_period_start=self._to_datetime(self._row_get(row, 'current_period_start', 6)),
                current_period_end=self._to_datetime(self._row_get(row, 'current_period_end', 7)),
                cancel_at_period_end=bool(self._row_get(row, 'cancel_at_period_end', 8)),
                cancellation_effective_date=self._to_datetime(self._row_get(row, 'cancellation_effective_date', 9)),
                created_at=self._to_datetime(self._row_get(row, 'created_at', 10)),
                updated_at=self._to_datetime(self._row_get(row, 'updated_at', 11)),
            )
        finally:
            conn.close()

    def record_subscription_event(self, event_type: str, payload: Dict[str, Any], stripe_event_id: str = None):
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        payload_json = json.dumps(payload)

        try:
            cur.execute(
                f"INSERT INTO subscription_events (event_type, stripe_event_id, payload) VALUES ({placeholder}, {placeholder}, {placeholder})",
                (event_type, stripe_event_id, payload_json),
            )
            conn.commit()
        finally:
            conn.close()

    def ensure_subscription_schema(self):
        """Ensure subscription plan and user subscription tables match the normalized schema."""
        conn = self.get_connection()
        cur = conn.cursor()

        try:
            plan_mapping = self._ensure_subscription_plans_schema(cur)
            self._ensure_user_subscriptions_schema(cur, plan_mapping)
            conn.commit()
        finally:
            conn.close()

    def _ensure_subscription_plans_schema(self, cur) -> Dict[str, str]:
        """Guarantee subscription_plans has normalized columns and return plan mapping for migrations."""
        mapping: Dict[str, str] = {}

        if not self._table_exists(cur, 'subscription_plans'):
            self._create_subscription_plans_table(cur)

        columns = self._get_table_columns(cur, 'subscription_plans')

        def add_column(column: str, definitions: Dict[str, str]):
            if column in columns:
                return

            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        f"ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS {column} {definitions['postgres']}"
                    )
                else:
                    cur.execute(
                        f"ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS {column} {definitions.get('mysql', definitions['postgres'])}"
                    )
            else:
                cur.execute(
                    f"ALTER TABLE subscription_plans ADD COLUMN {column} {definitions.get('sqlite', definitions['postgres'])}"
                )

            columns.add(column)

        def drop_column(column: str):
            if column not in columns:
                return
            if not self.use_rds:
                return

            statement = f"ALTER TABLE subscription_plans DROP COLUMN IF EXISTS {column}"
            cur.execute(statement)
            columns.discard(column)

        add_column(
            'plan_code',
            {
                'postgres': 'VARCHAR(50)',
                'mysql': 'VARCHAR(50)',
                'sqlite': 'TEXT',
            },
        )
        add_column(
            'name',
            {
                'postgres': 'VARCHAR(255)',
                'mysql': 'VARCHAR(255)',
                'sqlite': 'TEXT',
            },
        )
        add_column(
            'interval_months',
            {
                'postgres': 'INTEGER DEFAULT 12',
                'mysql': 'INT DEFAULT 12',
                'sqlite': 'INTEGER DEFAULT 12',
            },
        )
        add_column(
            'amount_cents',
            {
                'postgres': 'INTEGER DEFAULT 0',
                'mysql': 'INT DEFAULT 0',
                'sqlite': 'INTEGER DEFAULT 0',
            },
        )
        add_column(
            'stripe_price_id',
            {
                'postgres': 'VARCHAR(255)',
                'mysql': 'VARCHAR(255)',
                'sqlite': 'TEXT',
            },
        )
        add_column(
            'is_active',
            {
                'postgres': 'BOOLEAN DEFAULT TRUE',
                'mysql': 'TINYINT(1) DEFAULT 1',
                'sqlite': 'BOOLEAN DEFAULT 1',
            },
        )
        add_column(
            'created_at',
            {
                'postgres': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'mysql': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'sqlite': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            },
        )
        add_column(
            'updated_at',
            {
                'postgres': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'mysql': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'sqlite': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            },
        )

        drop_column('price_monthly')
        drop_column('price_quarterly')

        # Populate missing values and build mapping
        cur.execute('SELECT * FROM subscription_plans')
        rows = cur.fetchall()
        column_names = [desc[0] for desc in cur.description] if cur.description else []
        plan_rows: List[Dict[str, Any]] = [dict(zip(column_names, row)) for row in rows]

        existing_codes = {
            str(row.get('plan_code')).strip()
            for row in plan_rows
            if row.get('plan_code') and str(row.get('plan_code')).strip()
        }

        placeholder = '%s' if self.use_rds else '?'

        for index, row in enumerate(plan_rows, start=1):
            plan_id = row.get('id')
            original_code = row.get('plan_code')
            original_name = row.get('name')
            updates: Dict[str, Any] = {}

            fallback_name = row.get('plan_name') or f"Legacy Plan {plan_id or index}"

            if not original_name:
                updates['name'] = fallback_name
            else:
                fallback_name = original_name

            if not original_code or not str(original_code).strip():
                base_code = self._slugify_plan_code(fallback_name, f"legacy-plan-{plan_id or index}")
                candidate = base_code
                suffix = 1
                while candidate in existing_codes:
                    candidate = f"{base_code}-{suffix}"
                    suffix += 1
                updates['plan_code'] = candidate
                existing_codes.add(candidate)
            else:
                existing_codes.add(str(original_code).strip())

            interval_value = row.get('interval_months')
            if not interval_value or (isinstance(interval_value, (int, float)) and interval_value <= 0):
                interval_fallback = (
                    row.get('billing_interval_months')
                    or row.get('duration_months')
                    or 12
                )
                updates['interval_months'] = int(interval_fallback)

            amount_value = row.get('amount_cents')
            if amount_value in (None, '', 0, 0.0):
                amount_fallback = None
                for key in ['price_yearly', 'price_annual', 'price_year', 'price', 'price_monthly', 'price_quarterly']:
                    if key in row and row.get(key) not in (None, ''):
                        amount_fallback = row.get(key)
                        break
                updates['amount_cents'] = self._normalize_amount_to_cents(amount_fallback)

            if row.get('is_active') is None:
                updates['is_active'] = True

            if updates:
                set_clause = ', '.join(f"{column} = {placeholder}" for column in updates.keys())
                params = list(updates.values()) + [plan_id]
                cur.execute(
                    f"UPDATE subscription_plans SET {set_clause} WHERE id = {placeholder}",
                    params,
                )
                row.update(updates)

            final_code = str(row.get('plan_code')).strip() if row.get('plan_code') else None
            if original_code and final_code and str(original_code).lower() != final_code.lower():
                mapping[f"code:{str(original_code).lower()}"] = final_code

            self._register_plan_mapping(mapping, row, final_code)

        # Enforce uniqueness on plan_code where possible
        try:
            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_plans_plan_code ON subscription_plans (plan_code)"
                    )
                    cur.execute(
                        "ALTER TABLE subscription_plans ALTER COLUMN plan_code SET NOT NULL"
                    )
                else:
                    try:
                        cur.execute(
                            "CREATE UNIQUE INDEX idx_subscription_plans_plan_code ON subscription_plans (plan_code)"
                        )
                    except Exception:
                        pass
                    try:
                        cur.execute(
                            "ALTER TABLE subscription_plans MODIFY plan_code VARCHAR(50) NOT NULL"
                        )
                    except Exception:
                        pass
            else:
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_plans_plan_code ON subscription_plans (plan_code)"
                )
        except Exception:
            # Index/constraint creation should not block startup if it already exists or fails for legacy engines
            pass

        # Attempt to remove legacy plan_name column after copying
        if 'plan_name' in columns and self.use_rds:
            try:
                cur.execute('ALTER TABLE subscription_plans DROP COLUMN IF EXISTS plan_name')
            except Exception:
                pass

        return mapping

    def _ensure_user_subscriptions_schema(self, cur, plan_mapping: Dict[str, str]):
        if not self._table_exists(cur, 'user_subscriptions'):
            self._create_user_subscriptions_table(cur)
            return

        columns = self._get_table_columns(cur, 'user_subscriptions')

        def add_column(column: str, definitions: Dict[str, str]):
            if column in columns:
                return
            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        f"ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS {column} {definitions['postgres']}"
                    )
                else:
                    cur.execute(
                        f"ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS {column} {definitions.get('mysql', definitions['postgres'])}"
                    )
            else:
                cur.execute(
                    f"ALTER TABLE user_subscriptions ADD COLUMN {column} {definitions.get('sqlite', definitions['postgres'])}"
                )
            columns.add(column)

        add_column(
            'plan_code',
            {
                'postgres': 'VARCHAR(50)',
                'mysql': 'VARCHAR(50)',
                'sqlite': 'TEXT',
            },
        )
        add_column(
            'stripe_subscription_id',
            {
                'postgres': 'VARCHAR(255)',
                'mysql': 'VARCHAR(255)',
                'sqlite': 'TEXT',
            },
        )
        add_column(
            'stripe_customer_id',
            {
                'postgres': 'VARCHAR(255)',
                'mysql': 'VARCHAR(255)',
                'sqlite': 'TEXT',
            },
        )
        add_column(
            'status',
            {
                'postgres': "VARCHAR(30) DEFAULT 'inactive'",
                'mysql': "VARCHAR(30) DEFAULT 'inactive'",
                'sqlite': "TEXT DEFAULT 'inactive'",
            },
        )
        add_column(
            'current_period_start',
            {
                'postgres': 'TIMESTAMP NULL',
                'mysql': 'DATETIME NULL',
                'sqlite': 'DATETIME NULL',
            },
        )
        add_column(
            'current_period_end',
            {
                'postgres': 'TIMESTAMP NULL',
                'mysql': 'DATETIME NULL',
                'sqlite': 'DATETIME NULL',
            },
        )
        add_column(
            'cancel_at_period_end',
            {
                'postgres': 'BOOLEAN DEFAULT FALSE',
                'mysql': 'TINYINT(1) DEFAULT 0',
                'sqlite': 'BOOLEAN DEFAULT 0',
            },
        )
        add_column(
            'cancellation_effective_date',
            {
                'postgres': 'TIMESTAMP NULL',
                'mysql': 'DATETIME NULL',
                'sqlite': 'DATETIME NULL',
            },
        )
        add_column(
            'created_at',
            {
                'postgres': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'mysql': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'sqlite': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            },
        )
        add_column(
            'updated_at',
            {
                'postgres': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'mysql': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'sqlite': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            },
        )

        # Update legacy rows with plan codes and defaults
        cur.execute('SELECT * FROM user_subscriptions')
        rows = cur.fetchall()
        column_names = [desc[0] for desc in cur.description] if cur.description else []
        subscription_rows: List[Dict[str, Any]] = [dict(zip(column_names, row)) for row in rows]

        placeholder = '%s' if self.use_rds else '?'

        for index, row in enumerate(subscription_rows, start=1):
            sub_id = row.get('id')
            updates: Dict[str, Any] = {}
            resolved_plan_code = self._resolve_plan_code_for_subscription(
                row,
                plan_mapping,
                fallback=f"legacy-plan-{row.get('plan_id') or sub_id or index}",
            )

            if resolved_plan_code and row.get('plan_code') != resolved_plan_code:
                updates['plan_code'] = resolved_plan_code

            if not row.get('status'):
                updates['status'] = 'inactive'

            if row.get('cancel_at_period_end') is None:
                updates['cancel_at_period_end'] = False

            if updates:
                set_clause = ', '.join(f"{column} = {placeholder}" for column in updates.keys())
                params = list(updates.values()) + [sub_id]
                cur.execute(
                    f"UPDATE user_subscriptions SET {set_clause} WHERE id = {placeholder}",
                    params,
                )

        # Ensure unique constraint/index on user_id to prevent duplicates
        try:
            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        """
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint
                                WHERE conrelid = 'user_subscriptions'::regclass
                                AND conname = 'user_subscriptions_user_id_key'
                            ) THEN
                                ALTER TABLE user_subscriptions ADD CONSTRAINT user_subscriptions_user_id_key UNIQUE (user_id);
                            END IF;
                        END $$;
                        """
                    )
                else:
                    try:
                        cur.execute(
                            "ALTER TABLE user_subscriptions ADD UNIQUE INDEX idx_user_subscriptions_user_id (user_id)"
                        )
                    except Exception:
                        pass
            else:
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON user_subscriptions (user_id)"
                )
        except Exception:
            pass

    def _table_exists(self, cur, table_name: str) -> bool:
        try:
            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                            AND table_name = %s
                        )
                        """,
                        (table_name,),
                    )
                    result = cur.fetchone()
                    return bool(result[0]) if result else False
                else:
                    cur.execute("SHOW TABLES LIKE %s", (table_name,))
                    return cur.fetchone() is not None
            else:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
                return cur.fetchone() is not None
        except Exception:
            return False

    def _get_table_columns(self, cur, table_name: str) -> set:
        if not self._table_exists(cur, table_name):
            return set()

        if self.use_rds:
            if self.is_postgres:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = %s
                    """,
                    (table_name,),
                )
                return {row[0] for row in cur.fetchall()}
            else:
                cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
                return {row[0] for row in cur.fetchall()}
        else:
            cur.execute(f"PRAGMA table_info({table_name})")
            return {row[1] for row in cur.fetchall()}

    def _create_subscription_plans_table(self, cur):
        if self.use_rds:
            if self.is_postgres:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS subscription_plans (
                        id SERIAL PRIMARY KEY,
                        plan_code VARCHAR(50) UNIQUE NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        interval_months INTEGER NOT NULL,
                        amount_cents INTEGER NOT NULL,
                        stripe_price_id VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS subscription_plans (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        plan_code VARCHAR(50) NOT NULL UNIQUE,
                        name VARCHAR(255) NOT NULL,
                        interval_months INT NOT NULL,
                        amount_cents INT NOT NULL,
                        stripe_price_id VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    interval_months INTEGER NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    stripe_price_id TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _create_user_subscriptions_table(self, cur):
        if self.use_rds:
            if self.is_postgres:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_subscriptions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE,
                        plan_code VARCHAR(50) NOT NULL,
                        stripe_subscription_id VARCHAR(255),
                        stripe_customer_id VARCHAR(255),
                        status VARCHAR(30) NOT NULL DEFAULT 'inactive',
                        current_period_start TIMESTAMP NULL,
                        current_period_end TIMESTAMP NULL,
                        cancel_at_period_end BOOLEAN DEFAULT FALSE,
                        cancellation_effective_date TIMESTAMP NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (plan_code) REFERENCES subscription_plans (plan_code),
                        FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                    )
                    """
                )
            else:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_subscriptions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL UNIQUE,
                        plan_code VARCHAR(50) NOT NULL,
                        stripe_subscription_id VARCHAR(255),
                        stripe_customer_id VARCHAR(255),
                        status VARCHAR(30) NOT NULL DEFAULT 'inactive',
                        current_period_start DATETIME NULL,
                        current_period_end DATETIME NULL,
                        cancel_at_period_end BOOLEAN DEFAULT FALSE,
                        cancellation_effective_date DATETIME NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (plan_code) REFERENCES subscription_plans (plan_code),
                        FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                    ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
        else:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    plan_code TEXT NOT NULL,
                    stripe_subscription_id TEXT,
                    stripe_customer_id TEXT,
                    status TEXT NOT NULL DEFAULT 'inactive',
                    current_period_start DATETIME,
                    current_period_end DATETIME,
                    cancel_at_period_end BOOLEAN DEFAULT 0,
                    cancellation_effective_date DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_code) REFERENCES subscription_plans (plan_code),
                    FOREIGN KEY (user_id) REFERENCES userdata (id) ON DELETE CASCADE
                )
                """
            )

    def _slugify_plan_code(self, value: str, fallback: str) -> str:
        base = ''
        if value:
            base = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
        if not base:
            base = re.sub(r'[^a-z0-9]+', '-', fallback.lower()).strip('-') or 'legacy-plan'
        return base.replace('-', '_')

    def _normalize_amount_to_cents(self, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, Decimal):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(round(value))
        if isinstance(value, (bytes, bytearray, memoryview)):
            try:
                value = bytes(value).decode()
            except Exception:
                return 0
        if isinstance(value, str):
            cleaned = value.strip().replace(',', '')
            if not cleaned:
                return 0
            try:
                return int(round(float(cleaned)))
            except ValueError:
                digits = ''.join(re.findall(r'\d+', cleaned))
                return int(digits) if digits else 0
        return 0

    def _register_plan_mapping(self, mapping: Dict[str, str], row: Dict[str, Any], plan_code: Optional[str]):
        if not plan_code:
            return

        mapping[f"code:{plan_code.lower()}"] = plan_code

        original_code = row.get('plan_code')
        if original_code:
            mapping[f"code:{str(original_code).lower()}"] = plan_code

        plan_id = row.get('id')
        if plan_id is not None:
            mapping[f"id:{plan_id}"] = plan_code

        for key in ('plan_name', 'name'):
            if row.get(key):
                mapping[f"name:{str(row.get(key)).lower()}"] = plan_code

    def _resolve_plan_code_for_subscription(self, row: Dict[str, Any], mapping: Dict[str, str], fallback: str) -> str:
        if not mapping:
            return row.get('plan_code') or fallback

        candidates = []

        if row.get('plan_code'):
            candidates.append(f"code:{str(row['plan_code']).lower()}")

        if 'plan_id' in row and row.get('plan_id') is not None:
            candidates.append(f"id:{row['plan_id']}")

        if 'plan_name' in row and row.get('plan_name'):
            candidates.append(f"name:{str(row['plan_name']).lower()}")

        if 'name' in row and row.get('name'):
            candidates.append(f"name:{str(row['name']).lower()}")

        for candidate in candidates:
            if candidate in mapping:
                return mapping[candidate]

        return row.get('plan_code') or fallback

    def ensure_default_subscription_plans(self):
        """Ensure the canonical semi-annual and annual plans exist"""
        # Normalize schema before attempting to seed plans so legacy databases do not fail.
        try:
            self.ensure_subscription_schema()
        except Exception:
            # Continue even if normalization fails so existing behaviour is preserved.
            pass

        defaults = [
            (
                'plan_semiannual',
                'Semi-Annual Plan',
                6,
                0,
                settings.STRIPE_PRICE_6M,
            ),
            (
                'plan_annual',
                'Annual Plan',
                12,
                0,
                settings.STRIPE_PRICE_12M,
            ),
        ]

        for plan_code, name, months, amount_cents, price_id in defaults:
            # Only seed plan if stripe price id is provided or plan already exists
            existing = self.get_subscription_plan(plan_code)
            if price_id or existing:
                self.upsert_subscription_plan(
                    plan_code,
                    name,
                    months,
                    amount_cents if amount_cents else (existing.amount_cents if existing else 0),
                    price_id or (existing.stripe_price_id if existing else None),
                    True,
                )

    def list_subscription_events_since(self, since: datetime) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, event_type, stripe_event_id, payload, created_at FROM subscription_events WHERE created_at >= {placeholder}",
                (self._format_datetime(since),),
            )
            rows = cur.fetchall()
            events = []
            for row in rows:
                payload_raw = self._row_get(row, 'payload', 3)
                try:
                    payload_json = json.loads(payload_raw) if isinstance(payload_raw, (str, bytes)) else payload_raw
                except Exception:
                    payload_json = payload_raw
                events.append({
                    'id': self._row_get(row, 'id', 0),
                    'event_type': self._row_get(row, 'event_type', 1),
                    'stripe_event_id': self._row_get(row, 'stripe_event_id', 2),
                    'payload': payload_json,
                    'created_at': self._to_datetime(self._row_get(row, 'created_at', 4)),
                })
            return events
        finally:
            conn.close()

    def list_user_subscriptions(self, since: datetime = None) -> List[UserSubscription]:
        conn = self.get_connection()
        cur = conn.cursor()

        try:
            if since:
                cur.execute(
                    "SELECT id, user_id, plan_code, stripe_subscription_id, stripe_customer_id, status, current_period_start, "
                    "current_period_end, cancel_at_period_end, cancellation_effective_date, created_at, updated_at "
                    "FROM user_subscriptions WHERE created_at >= ?" if not self.use_rds else
                    "SELECT id, user_id, plan_code, stripe_subscription_id, stripe_customer_id, status, current_period_start, "
                    "current_period_end, cancel_at_period_end, cancellation_effective_date, created_at, updated_at FROM user_subscriptions WHERE created_at >= %s",
                    (self._format_datetime(since),),
                )
            else:
                cur.execute(
                    "SELECT id, user_id, plan_code, stripe_subscription_id, stripe_customer_id, status, current_period_start, "
                    "current_period_end, cancel_at_period_end, cancellation_effective_date, created_at, updated_at FROM user_subscriptions"
                )
            rows = cur.fetchall()
            subs = []
            for row in rows:
                subs.append(
                    UserSubscription(
                        id=self._row_get(row, 'id', 0),
                        user_id=self._row_get(row, 'user_id', 1),
                        plan_code=self._row_get(row, 'plan_code', 2),
                        stripe_subscription_id=self._row_get(row, 'stripe_subscription_id', 3),
                        stripe_customer_id=self._row_get(row, 'stripe_customer_id', 4),
                        status=self._row_get(row, 'status', 5),
                        current_period_start=self._to_datetime(self._row_get(row, 'current_period_start', 6)),
                        current_period_end=self._to_datetime(self._row_get(row, 'current_period_end', 7)),
                        cancel_at_period_end=bool(self._row_get(row, 'cancel_at_period_end', 8)),
                        cancellation_effective_date=self._to_datetime(self._row_get(row, 'cancellation_effective_date', 9)),
                        created_at=self._to_datetime(self._row_get(row, 'created_at', 10)),
                        updated_at=self._to_datetime(self._row_get(row, 'updated_at', 11)),
                    )
                )
            return subs
        finally:
            conn.close()

    # Profile photos
    def upsert_user_profile_photo(
        self,
        user_id: int,
        object_key: str,
        url: str,
        storage_backend: str,
        etag: str = None,
    ) -> UserProfilePhoto:
        conn = self.get_connection()
        cur = conn.cursor()

        try:
            if self.use_rds:
                if self.is_postgres:
                    cur.execute(
                        """
                            INSERT INTO user_profile_photos (user_id, object_key, url, storage_backend, etag)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (user_id) DO UPDATE SET
                                object_key = EXCLUDED.object_key,
                                url = EXCLUDED.url,
                                storage_backend = EXCLUDED.storage_backend,
                                etag = EXCLUDED.etag,
                                last_updated = CURRENT_TIMESTAMP
                        """,
                        (user_id, object_key, url, storage_backend, etag),
                    )
                else:
                    cur.execute(
                        """
                            INSERT INTO user_profile_photos (user_id, object_key, url, storage_backend, etag)
                            VALUES (%s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                object_key = VALUES(object_key),
                                url = VALUES(url),
                                storage_backend = VALUES(storage_backend),
                                etag = VALUES(etag),
                                last_updated = CURRENT_TIMESTAMP
                        """,
                        (user_id, object_key, url, storage_backend, etag),
                    )
            else:
                cur.execute(
                    """
                        INSERT INTO user_profile_photos (user_id, object_key, url, storage_backend, etag)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            object_key = excluded.object_key,
                            url = excluded.url,
                            storage_backend = excluded.storage_backend,
                            etag = excluded.etag,
                            last_updated = CURRENT_TIMESTAMP
                    """,
                    (user_id, object_key, url, storage_backend, etag),
                )
            conn.commit()
        finally:
            conn.close()

        return self.get_user_profile_photo(user_id)

    def get_user_profile_photo(self, user_id: int) -> Optional[UserProfilePhoto]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, user_id, object_key, url, storage_backend, etag, last_updated FROM user_profile_photos WHERE user_id = {placeholder}",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return UserProfilePhoto(
                id=self._row_get(row, 'id', 0),
                user_id=self._row_get(row, 'user_id', 1),
                object_key=self._row_get(row, 'object_key', 2),
                url=self._row_get(row, 'url', 3),
                storage_backend=self._row_get(row, 'storage_backend', 4),
                etag=self._row_get(row, 'etag', 5),
                last_updated=self._to_datetime(self._row_get(row, 'last_updated', 6)),
            )
        finally:
            conn.close()

    # Metrics helpers
    def get_users_created_since(self, since: datetime) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, created_at FROM userdata WHERE created_at >= {placeholder}",
                (self._format_datetime(since),),
            )
            rows = cur.fetchall()
            return [
                {
                    'id': self._row_get(row, 'id', 0),
                    'created_at': self._to_datetime(self._row_get(row, 'created_at', 1)),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def get_projects_created_since(self, since: datetime) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()

        try:
            cur.execute(
                f"SELECT id, project_id, created_at FROM projects WHERE created_at >= {placeholder}",
                (self._format_datetime(since),),
            )
            rows = cur.fetchall()
            return [
                {
                    'id': self._row_get(row, 'id', 0),
                    'project_id': self._row_get(row, 'project_id', 1),
                    'created_at': self._to_datetime(self._row_get(row, 'created_at', 2)),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def count_active_subscriptions(self) -> int:
        conn = self.get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                "SELECT COUNT(*) FROM user_subscriptions WHERE status IN ('active', 'trialing')"
            )
            row = cur.fetchone()
            if isinstance(row, dict):
                return list(row.values())[0]
            return row[0] if row else 0
        finally:
            conn.close()

    def count_total_users(self) -> int:
        conn = self.get_connection()
        cur = conn.cursor()

        try:
            cur.execute("SELECT COUNT(*) FROM userdata")
            row = cur.fetchone()
            if isinstance(row, dict):
                return list(row.values())[0]
            return row[0] if row else 0
        finally:
            conn.close()

    def count_total_projects(self) -> int:
        conn = self.get_connection()
        cur = conn.cursor()

        try:
            cur.execute("SELECT COUNT(*) FROM projects")
            row = cur.fetchone()
            if isinstance(row, dict):
                return list(row.values())[0]
            return row[0] if row else 0
        finally:
            conn.close()

    def update_project_details(self, project_id: str, name: str = None, description: str = None):
        """Update project details"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                # MySQL syntax for updating timestamp
                if name and description:
                    cur.execute(
                        f"UPDATE projects SET name = {placeholder}, description = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE project_id = {placeholder}",
                        (name, description, project_id)
                    )
                elif name:
                    cur.execute(
                        f"UPDATE projects SET name = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE project_id = {placeholder}",
                        (name, project_id)
                    )
                elif description:
                    cur.execute(
                        f"UPDATE projects SET description = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE project_id = {placeholder}",
                        (description, project_id)
                    )
            else:
                # SQLite syntax
                if name and description:
                    cur.execute(
                        "UPDATE projects SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
                        (name, description, project_id)
                    )
                elif name:
                    cur.execute(
                        "UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
                        (name, project_id)
                    )
                elif description:
                    cur.execute(
                        "UPDATE projects SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
                        (description, project_id)
                    )
            conn.commit()
        finally:
            conn.close()
    
    # Document management methods
    def create_document(self, doc_id: str, filename: str, file_id: str, pages: int, chunks_indexed: int, user_id: int, pdf_path: str = None, vector_path: str = None) -> int:
        """Create a new document record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute(
                    f"INSERT INTO documents (doc_id, filename, file_id, pages, chunks_indexed, user_id) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (doc_id, filename, file_id, pages, chunks_indexed, user_id)
                )
            else:
                # Use old schema for backward compatibility
                cur.execute(
                    f"INSERT INTO documents (doc_id, filename, pdf_path, vector_path, pages, chunks_indexed, user_id) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (doc_id, filename, pdf_path or "", vector_path or "", pages, chunks_indexed, user_id)
                )
            
            conn.commit()
            
            # Get the new document's ID
            cur.execute(f"SELECT id FROM documents WHERE doc_id = {placeholder}", (doc_id,))
            document = cur.fetchone()
            return document[0] if document else None
            
        finally:
            conn.close()
    
    def update_document_chunks_indexed(self, doc_id: str, chunks_indexed: int) -> bool:
        """Update the chunks_indexed count for a document"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            placeholder = self._get_placeholder()
            
            cur.execute(
                f"UPDATE documents SET chunks_indexed = {placeholder} WHERE doc_id = {placeholder}",
                (chunks_indexed, doc_id)
            )
            conn.commit()
            
            return cur.rowcount > 0
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error updating document chunks count: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_document_by_doc_id(self, doc_id: str) -> Optional[Document]:
        """Get document by doc_id"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute(f"""
                    SELECT id, doc_id, filename, file_id, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    WHERE doc_id = {placeholder}
                """, (doc_id,))
                row = cur.fetchone()
                
                if row:
                    return Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
            else:
                # Use old schema for backward compatibility (SQLite/MySQL)
                cur.execute(f"""
                    SELECT id, doc_id, filename, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    WHERE doc_id = {placeholder}
                """, (doc_id,))
                row = cur.fetchone()
                
                if row:
                    return Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
                    )
            return None
            
        finally:
            conn.close()
    
    def get_user_documents(self, user_id: int) -> List[Document]:
        """Get all documents for a user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute(
                    f"SELECT id, doc_id, filename, file_id, pages, chunks_indexed, status, user_id, created_at, updated_at FROM documents WHERE user_id = {placeholder} ORDER BY created_at DESC",
                    (user_id,)
                )
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
            else:
                # Use old schema for backward compatibility
                cur.execute(
                    f"SELECT id, doc_id, filename, pages, chunks_indexed, status, user_id, created_at, updated_at FROM documents WHERE user_id = {placeholder} ORDER BY created_at DESC",
                    (user_id,)
                )
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
                    )
                    for row in rows
                ]
            
        finally:
            conn.close()
    
    def get_all_documents(self) -> List[Document]:
        """Get all documents in the system"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            if self.is_postgres:
                # Use new schema with file_id
                cur.execute("""
                    SELECT id, doc_id, filename, file_id, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    ORDER BY created_at DESC
                """)
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
            else:
                # Use old schema for backward compatibility
                cur.execute("""
                    SELECT id, doc_id, filename, pages, chunks_indexed, status, user_id, created_at, updated_at 
                    FROM documents 
                    ORDER BY created_at DESC
                """)
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
                    )
                    for row in rows
                ]
            
        finally:
            conn.close()
    
    def update_document_status(self, doc_id: str, status: str) -> bool:
        """Update document status"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(
                    f"UPDATE documents SET status = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE doc_id = {placeholder}",
                    (status, doc_id)
                )
            else:
                cur.execute(
                    "UPDATE documents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE doc_id = ?",
                    (status, doc_id)
                )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def update_document_pages(self, doc_id: str, pages: int) -> bool:
        """Update document page count"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds:
                cur.execute(
                    f"UPDATE documents SET pages = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE doc_id = {placeholder}",
                    (pages, doc_id)
                )
            else:
                cur.execute(
                    "UPDATE documents SET pages = ?, updated_at = CURRENT_TIMESTAMP WHERE doc_id = ?",
                    (pages, doc_id)
                )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document record"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"DELETE FROM documents WHERE doc_id = {placeholder}", (doc_id,))
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project record (cascades to project_documents)"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"DELETE FROM projects WHERE project_id = {placeholder}", (project_id,))
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    # Project-Document relationship methods
    def add_document_to_project(self, project_id: str, doc_id: str) -> bool:
        """Add a document to a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"INSERT INTO project_documents (project_id, doc_id) VALUES ({placeholder}, {placeholder})",
                (project_id, doc_id)
            )
            conn.commit()
            return cur.rowcount > 0
            
        except Exception as e:
            # Handle duplicate key error gracefully
            if "Duplicate" in str(e) or "UNIQUE constraint" in str(e):
                return False  # Already exists
            raise e
        finally:
            conn.close()
    
    def remove_document_from_project(self, project_id: str, doc_id: str) -> bool:
        """Remove a document from a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"DELETE FROM project_documents WHERE project_id = {placeholder} AND doc_id = {placeholder}",
                (project_id, doc_id)
            )
            conn.commit()
            return cur.rowcount > 0
            
        finally:
            conn.close()
    
    def get_project_documents(self, project_id: str) -> List[Document]:
        """Get all documents for a project"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            if self.use_rds and self.is_postgres:
                # Use new schema with file_id
                cur.execute(f"""
                    SELECT d.id, d.doc_id, d.filename, d.file_id, d.pages, d.chunks_indexed, d.status, d.user_id, d.created_at, d.updated_at
                    FROM documents d
                    INNER JOIN project_documents pd ON d.doc_id = pd.doc_id
                    WHERE pd.project_id = {placeholder}
                    ORDER BY pd.created_at ASC
                """, (project_id,))
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id=row[3],
                        pages=row[4],
                        chunks_indexed=row[5],
                        status=row[6],
                        user_id=row[7],
                        created_at=row[8],
                        updated_at=row[9]
                    )
                    for row in rows
                ]
            else:
                # Use old schema for backward compatibility
                cur.execute(f"""
                    SELECT d.id, d.doc_id, d.filename, d.pages, d.chunks_indexed, d.status, d.user_id, d.created_at, d.updated_at 
                    FROM documents d
                    INNER JOIN project_documents pd ON d.doc_id = pd.doc_id
                    WHERE pd.project_id = {placeholder}
                    ORDER BY pd.created_at ASC
                """, (project_id,))
                rows = cur.fetchall()
                
                return [
                    Document(
                        id=row[0],
                        doc_id=row[1],
                        filename=row[2],
                        file_id="",  # Not available in old schema
                        pages=row[3],
                        chunks_indexed=row[4],
                        status=row[5],
                        user_id=row[6],
                        created_at=row[7],
                        updated_at=row[8]
                    )
                    for row in rows
                ]
            
        finally:
            conn.close()
    
    def get_document_projects(self, doc_id: str) -> List[Project]:
        """Get all projects that contain a specific document"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(f"""
                SELECT p.id, p.project_id, p.name, p.description, p.user_id, p.doc_ids, p.created_at, p.updated_at 
                FROM projects p
                INNER JOIN project_documents pd ON p.project_id = pd.project_id
                WHERE pd.doc_id = {placeholder}
                ORDER BY p.created_at DESC
            """, (doc_id,))
            rows = cur.fetchall()
            
            result = []
            for row in rows:
                # Parse doc_ids from JSON string if present
                doc_ids = None
                if row[5]:
                    try:
                        doc_ids = json.loads(row[5])
                    except json.JSONDecodeError:
                        doc_ids = [row[5]]  # Fallback to old single doc_id format
                
                result.append(Project(
                    id=row[0],
                    project_id=row[1],
                    name=row[2],
                    description=row[3],
                    user_id=row[4],
                    doc_ids=doc_ids,
                    created_at=row[6],
                    updated_at=row[7]
                ))
            
            return result
            
        finally:
            conn.close()
    
    def _migrate_email_verification_schema(self):
        """Add email verification columns to existing userdata table"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            if self.use_rds:
                if self.is_postgres:
                    # Check if email verification columns exist in PostgreSQL
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = 'userdata' 
                        AND column_name = 'is_verified'
                    """)
                    
                    column_exists = cur.fetchone()[0] > 0
                    
                    if not column_exists:
                        print("Adding email verification columns to userdata table (PostgreSQL)...")
                        cur.execute("ALTER TABLE userdata ADD COLUMN is_verified BOOLEAN DEFAULT FALSE")
                        cur.execute("ALTER TABLE userdata ADD COLUMN verification_token VARCHAR(255)")
                        cur.execute("ALTER TABLE userdata ADD COLUMN verification_token_expires TIMESTAMP NULL")
                        
                        # Set Google OAuth users as verified by default
                        cur.execute("UPDATE userdata SET is_verified = TRUE WHERE google_id IS NOT NULL")
                        
                        conn.commit()
                        print("Email verification columns added successfully")
                    else:
                        print("Email verification columns already exist in userdata table")
                else:
                    # MySQL logic
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'userdata' 
                        AND COLUMN_NAME = 'is_verified'
                    """, (settings.DB_NAME,))
                    
                    column_exists = cur.fetchone()[0] > 0
                    
                    if not column_exists:
                        print("Adding email verification columns to userdata table (MySQL)...")
                        cur.execute("ALTER TABLE userdata ADD COLUMN is_verified BOOLEAN DEFAULT FALSE")
                        cur.execute("ALTER TABLE userdata ADD COLUMN verification_token VARCHAR(255)")
                        cur.execute("ALTER TABLE userdata ADD COLUMN verification_token_expires TIMESTAMP NULL")
                        
                        # Set Google OAuth users as verified by default
                        cur.execute("UPDATE userdata SET is_verified = TRUE WHERE google_id IS NOT NULL")
                        
                        conn.commit()
                        print("Email verification columns added successfully")
                    else:
                        print("Email verification columns already exist in userdata table")
            else:
                # Check if email verification columns exist in SQLite
                cur.execute("PRAGMA table_info(userdata)")
                columns = [row[1] for row in cur.fetchall()]
                
                if 'is_verified' not in columns:
                    print("Adding email verification columns to userdata table (SQLite)...")
                    cur.execute("ALTER TABLE userdata ADD COLUMN is_verified BOOLEAN DEFAULT 0")
                    cur.execute("ALTER TABLE userdata ADD COLUMN verification_token VARCHAR(255)")
                    cur.execute("ALTER TABLE userdata ADD COLUMN verification_token_expires DATETIME")
                    
                    # Set Google OAuth users as verified by default
                    cur.execute("UPDATE userdata SET is_verified = 1 WHERE google_id IS NOT NULL")
                    
                    conn.commit()
                    print("Email verification columns added successfully")
                else:
                    print("Email verification columns already exist in userdata table")
                    
        except Exception as e:
            print(f"Email verification migration error: {e}")
            if conn:
                conn.rollback()
            # Don't raise the exception to prevent breaking initialization
        finally:
            if conn:
                conn.close()
    
    def _migrate_session_schema(self):
        """Migrate existing tables to support enhanced session management"""
        conn = None
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            if self.use_rds:
                if self.is_postgres:
                    # PostgreSQL migration logic
                    # Check if chat_sessions table exists
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_name = 'chat_sessions'
                    """)
                    
                    table_exists = cur.fetchone()[0] > 0
                    
                    if not table_exists:
                        print("Creating chat_sessions table (PostgreSQL)...")
                        # Table is already created in init_database for PostgreSQL
                        print("chat_sessions table already created in init_database")
                    
                    # Check if context columns exist in chathistory table
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = 'chathistory' 
                        AND column_name = 'context_type'
                    """)
                    
                    context_columns_exist = cur.fetchone()[0] > 0
                    
                    if not context_columns_exist:
                        print("Adding context columns to chathistory table (PostgreSQL)...")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_type VARCHAR(20) CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL'))")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_id VARCHAR(255)")
                        cur.execute("CREATE INDEX IF NOT EXISTS idx_chathistory_context ON chathistory (context_type, context_id)")
                        conn.commit()
                        print("Context columns added to chathistory table successfully")
                else:
                    # MySQL migration logic
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.TABLES 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'chat_sessions'
                    """, (settings.DB_NAME,))
                    
                    table_exists = cur.fetchone()[0] > 0
                    
                    if not table_exists:
                        print("Creating chat_sessions table (MySQL)...")
                        cur.execute("""
                            CREATE TABLE chat_sessions(
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                session_id VARCHAR(255) UNIQUE NOT NULL,
                                user_id INT NOT NULL,
                                context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NOT NULL,
                                context_id VARCHAR(255) NULL,
                                is_active BOOLEAN DEFAULT TRUE,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                                metadata JSON NULL,
                                FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE,
                                INDEX idx_user_context (user_id, context_type, context_id),
                                INDEX idx_session_id (session_id),
                                INDEX idx_last_activity (last_activity),
                                INDEX idx_active_sessions (user_id, is_active)
                            ) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                        """)
                        conn.commit()
                        print("chat_sessions table created successfully")
                    
                    # Check if context columns exist in chathistory table
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = %s 
                        AND TABLE_NAME = 'chathistory' 
                        AND COLUMN_NAME = 'context_type'
                    """, (settings.DB_NAME,))
                    
                    context_columns_exist = cur.fetchone()[0] > 0
                    
                    if not context_columns_exist:
                        print("Adding context columns to chathistory table (MySQL)...")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_type ENUM('PROJECT', 'DOCUMENT', 'GENERAL') NULL")
                        cur.execute("ALTER TABLE chathistory ADD COLUMN context_id VARCHAR(255) NULL")
                        cur.execute("CREATE INDEX idx_chathistory_context ON chathistory (context_type, context_id)")
                        conn.commit()
                        print("Context columns added to chathistory table successfully")
                    
            else:
                # Check if chat_sessions table exists in SQLite
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'")
                table_exists = cur.fetchone() is not None
                
                if not table_exists:
                    print("Creating chat_sessions table (SQLite)...")
                    cur.execute("""
                        CREATE TABLE chat_sessions(
                            id INTEGER PRIMARY KEY,
                            session_id TEXT UNIQUE NOT NULL,
                            user_id INTEGER NOT NULL,
                            context_type TEXT NOT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL')),
                            context_id TEXT NULL,
                            is_active BOOLEAN DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                            metadata TEXT NULL,
                            FOREIGN KEY (user_id) REFERENCES userdata(id) ON DELETE CASCADE
                        )
                    """)
                    
                    # Create indexes
                    cur.execute("CREATE INDEX idx_chat_sessions_user_context ON chat_sessions (user_id, context_type, context_id)")
                    cur.execute("CREATE INDEX idx_chat_sessions_session_id ON chat_sessions (session_id)")
                    cur.execute("CREATE INDEX idx_chat_sessions_last_activity ON chat_sessions (last_activity)")
                    cur.execute("CREATE INDEX idx_chat_sessions_active ON chat_sessions (user_id, is_active)")
                    
                    conn.commit()
                    print("chat_sessions table created successfully")
                
                # Check if context columns exist in chathistory table
                cur.execute("PRAGMA table_info(chathistory)")
                columns = [row[1] for row in cur.fetchall()]
                
                if 'context_type' not in columns:
                    print("Adding context columns to chathistory table (SQLite)...")
                    cur.execute("ALTER TABLE chathistory ADD COLUMN context_type TEXT NULL CHECK (context_type IN ('PROJECT', 'DOCUMENT', 'GENERAL') OR context_type IS NULL)")
                    cur.execute("ALTER TABLE chathistory ADD COLUMN context_id TEXT NULL")
                    cur.execute("CREATE INDEX idx_chathistory_context ON chathistory (context_type, context_id)")
                    conn.commit()
                    print("Context columns added to chathistory table successfully")
                    
        except Exception as e:
            print(f"Session schema migration error: {e}")
            if conn:
                conn.rollback()
            # Don't raise the exception to prevent breaking initialization
        finally:
            if conn:
                conn.close()
    
    # Email verification methods
    def create_verification_token(self, user_id: int, token: str, expires_at: datetime) -> bool:
        """Create or update verification token for user"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"UPDATE userdata SET verification_token = {placeholder}, verification_token_expires = {placeholder} WHERE id = {placeholder}",
                (token, expires_at, user_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    
    def get_user_by_verification_token(self, token: str) -> Optional[User]:
        """Get user by verification token"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"SELECT id, firstname, lastname, email, password, google_id, is_verified, verification_token, verification_token_expires, created_at FROM userdata WHERE verification_token = {placeholder}",
                (token,)
            )
            row = cur.fetchone()
            
            if row:
                return User(
                    id=row[0],
                    firstname=row[1],
                    lastname=row[2],
                    email=row[3],
                    password=row[4],
                    google_id=row[5],
                    is_verified=bool(row[6]),
                    verification_token=row[7],
                    verification_token_expires=row[8],
                    created_at=row[9]
                )
            return None
            
        finally:
            conn.close()
    
    def verify_user_email(self, user_id: int) -> bool:
        """Mark user email as verified and clear verification token"""
        conn = self.get_connection()
        cur = conn.cursor()
        placeholder = self._get_placeholder()
        
        try:
            cur.execute(
                f"UPDATE userdata SET is_verified = {1 if not self.use_rds else 'TRUE'}, verification_token = NULL, verification_token_expires = NULL WHERE id = {placeholder}",
                (user_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    
    def clear_expired_verification_tokens(self):
        """Clear expired verification tokens"""
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            if self.use_rds:
                cur.execute(
                    "UPDATE userdata SET verification_token = NULL, verification_token_expires = NULL WHERE verification_token_expires < NOW()"
                )
            else:
                cur.execute(
                    "UPDATE userdata SET verification_token = NULL, verification_token_expires = NULL WHERE verification_token_expires < datetime('now')"
                )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

# Global database manager instance
db_manager = DatabaseManager()
