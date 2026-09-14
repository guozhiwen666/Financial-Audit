"""附件文件存储（PRD 2.7.9 附件模块、2.7.14 安全边界、16 安全边界）。

职责：附件的保存、读取与删除，以及上传前的格式与大小校验。
边界：本模块只落文件，不写数据库记录（附件记录属单据模块）；下载时的访问权限校验由服务层完成。
"""

import hashlib  # 内容哈希：用于去重命名与重复票据比对
from pathlib import Path

from config.config import storage_config  # 附件存储根目录

__all__ = ["ALLOWED_SUFFIXES", "MAX_FILE_SIZE", "validate_upload", "save", "read",
           "delete", "absolute_path", "root_dir"]

# PRD 2.7.2：非结构化附件支持 PDF、PNG、JPG 三种格式
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}
# PRD 16 要求校验文件大小，但未规定上限，故此处约定单附件 20 MB
MAX_FILE_SIZE = 20 * 1024 * 1024


def root_dir() -> Path:
    """返回附件存储根目录（相对路径按项目根目录解析），不存在时自动创建。"""
    # 步骤 1：相对路径一律相对项目根目录，避免受启动工作目录影响
    root = Path(storage_config.root_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parent.parent / root
    # 步骤 2：确保目录存在
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_upload(file_name: str, file_size: int) -> list[str]:
    """校验附件格式与大小，返回错误说明列表（空列表表示通过）。"""
    errors: list[str] = []
    # 步骤 1：格式校验——限定 PRD 2.7.2 列举的三种格式
    suffix = Path(file_name or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        errors.append("不支持的文件格式 %s，仅支持 PDF、PNG、JPG" % (suffix or "（无扩展名）"))
    # 步骤 2：内容非空校验
    if file_size <= 0:
        errors.append("文件内容为空")
    # 步骤 3：大小上限校验（PRD 16）
    elif file_size > MAX_FILE_SIZE:
        errors.append("文件大小 %d 字节超过上限 %d MB" % (file_size, MAX_FILE_SIZE // 1024 // 1024))
    return errors


def absolute_path(relative_path: str) -> Path:
    """把存储相对路径解析为绝对路径，并拦截目录穿越（PRD 16 校验文件路径）。"""
    # 步骤 1：解析后必须仍位于存储根目录之内，否则视为非法路径
    root = root_dir().resolve()
    target = (root / relative_path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("非法的附件路径：%s" % relative_path)
    return target


def save(document_id: int, file_name: str, content: bytes) -> tuple[str, int, str]:
    """保存附件内容，返回 (存储相对路径, 字节数, 内容哈希)。"""
    # 步骤 1：以内容哈希命名，天然去重且避免同名文件互相覆盖
    digest = hashlib.sha256(content).hexdigest()
    relative = "%d/%s%s" % (document_id, digest, Path(file_name).suffix.lower())
    # 步骤 2：按单据分目录落盘
    target = absolute_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return relative, len(content), digest


def read(relative_path: str) -> bytes:
    """读取附件内容（路径非法或文件不存在时抛错，由服务层转为错误响应）。"""
    return absolute_path(relative_path).read_bytes()


def delete(relative_path: str) -> bool:
    """删除附件文件，返回是否确实删除了文件。"""
    # 步骤 1：路径非法时直接返回 False，不向上抛错——删除失败不应阻断记录删除
    try:
        target = absolute_path(relative_path)
    except ValueError:
        return False
    # 步骤 2：文件存在才删除
    if target.is_file():
        target.unlink()
        return True
    return False
