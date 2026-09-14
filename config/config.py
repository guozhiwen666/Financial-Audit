import os
from dataclasses import dataclass

from dotenv import load_dotenv

# .env 位于项目根目录（本文件在 config/ 下，故向上取一级）
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=env_path, override=True)

@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    vl_model: str
    llm_model: str
    item_model: str
    llm_temperature: float

llm_config = LLMConfig(
    base_url=os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
    vl_model=os.getenv("VL_MODEL"),
    llm_model=os.getenv("LLM_DEFAULT_MODEL"),
    item_model=os.getenv("ITEM_MODEL"),
    llm_temperature=float(os.getenv("LLM_DEFAULT_TEMPERATURE", 0.1))
)

@dataclass
class MinIOConfig:
    endpoint: str
    access_key: str
    secret_key: str
    bucket_name: str
    img_dir: str

minio_config = MinIOConfig(
    endpoint=os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    bucket_name=os.getenv("MINIO_BUCKET_NAME"),
    img_dir=os.getenv("MINIO_IMG_DIR"),
)

@dataclass
class EmbeddingConfig:
    bge_m3_path: str
    bge_m3: str
    bge_device: str
    bge_fp16: bool

embedding_config = EmbeddingConfig(
    bge_m3_path=os.getenv('BGE_M3_PATH'),
    bge_m3=os.getenv('BGE_M3'),
    bge_device=os.getenv('BGE_DEVICE'),
    # 兼容常见的数字/字符串格式
    bge_fp16=(os.getenv('BGE_FP16') or '').strip().lower() in ('1', 'true')
)

@dataclass
class MilvusConfig:
    milvus_url: str
    chunk_collection: str
    item_name_collection: str

milvus_config = MilvusConfig(
    milvus_url=os.getenv("MILVUS_URL"),
    chunk_collection=os.getenv("CHUNKS_COLLECTION"),
    item_name_collection=os.getenv("ITEM_NAME_COLLECTION"),
)

@dataclass
class MongoConfig:
    mongo_url: str
    mongo_db_name: str

mongo_config = MongoConfig(
    mongo_url=os.getenv('MONGO_URL'),
    mongo_db_name=os.getenv('MONGO_DB_NAME'),
)

@dataclass
class McpConfig:
    mcp_base_url: str
    api_key: str

mcp_config = McpConfig(
    mcp_base_url=os.getenv("MCP_DASHSCOPE_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY")
)

@dataclass
class EmbeddingHttpConfig:
    api_key: str
    dashscope_url: str
    model: str
    dimension: int
    batch_size: int

embedding_http_config = EmbeddingHttpConfig(
    api_key=os.getenv("TEXT_EMBEDDING_API_KEY"),
    dashscope_url=os.getenv("TEXT_EMBEDDING_DASHSCOPE_URL"),
    model=os.getenv("TEXT_EMBEDDING_MODEL"),
    dimension=int(os.getenv("TEXT_EMBEDDING_DIMENSION", 1024)),
    batch_size=int(os.getenv("TEXT_EMBEDDING_BATCH_SIZE", 10))
)

@dataclass
class RerankerHttpConfig:
    model: str
    instruct: str
    api_key: str
    base_url: str

reranker_http_config = RerankerHttpConfig(
    model=os.getenv('TEXT_RERANK_MODEL'),
    instruct=os.getenv('TEXT_RERANK_INSTRUCT'),
    api_key=os.getenv('OPENAI_API_KEY'),
    base_url=os.getenv('OPENAI_BASE_URL_DASHSCOPE')
)

@dataclass
class FileUploadConfig:
    data_based_root_dir: str

file_upload_config = FileUploadConfig(
    data_based_root_dir=os.getenv('DATA_BASED_ROOT_DIR')
)

@dataclass
class DatabaseConfig:
    """项目数据库配置：系统独立保存用户、单据、附件、审批、分析与审计数据（PRD 2.7.14）。"""
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str

database_config = DatabaseConfig(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "financial_audit"),
    charset=os.getenv("DB_CHARSET", "utf8mb4"),
)

@dataclass
class AuthConfig:
    """认证配置：访问令牌须设置有效期与撤销机制（PRD 2.7.14）。"""
    secret_key: str
    algorithm: str
    expire_minutes: int

auth_config = AuthConfig(
    secret_key=os.getenv("JWT_SECRET_KEY", ""),
    algorithm="HS256",
    expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", 120)),
)

@dataclass
class StorageConfig:
    """附件存储配置：附件独立保存并按权限访问（PRD 2.7.14）。"""
    root_dir: str

storage_config = StorageConfig(
    root_dir=os.getenv("STORAGE_ROOT_DIR", "storage")
)

