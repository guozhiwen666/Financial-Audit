"""数据库访问层：连接管理、事务边界与 SQL 执行助手（PRD 11 章后端模块的公共依赖）。

事务边界依据 PRD 11.1：提交单据时「快照 + 实例 + 首任务」须在同一事务内完成，任一失败整体回滚。
故本模块用 ``transaction()`` 承载跨表写入，仓储方法自动并入当前事务（见 ``current_connection``）。
所有写操作使用参数化 SQL，禁止字符串拼接（PRD 16 安全边界）。
"""

import contextvars  # 承载当前事务连接，使仓储方法自动并入外层事务

import pymysql  # 已声明依赖（pyproject.toml）

from config.config import database_config  # 数据库配置（config/config.py）

__all__ = ["connect", "transaction", "current_connection", "query", "query_one", "execute"]

# 当前事务连接：不处于事务中时为 None，此时各助手自行建连并在用后关闭
_current_connection: contextvars.ContextVar = contextvars.ContextVar("db_connection", default=None)


def connect() -> "pymysql.connections.Connection":
    """按配置建立一个新的数据库连接（返回字典游标，便于按列名取值）。"""
    # 步骤 1：从配置读取连接参数，密钥不出现在代码中
    return pymysql.connect(
        host=database_config.host,
        port=database_config.port,
        user=database_config.user,
        password=database_config.password,
        database=database_config.database,
        charset=database_config.charset,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


class _Transaction:
    """事务上下文管理器：块内所有数据库操作共用同一连接，异常时整体回滚。"""

    def __init__(self) -> None:
        self.connection = None
        self.token = None

    def __enter__(self) -> "pymysql.connections.Connection":
        # 步骤 1：建立连接并登记为当前事务连接，供块内仓储方法复用
        self.connection = connect()
        self.token = _current_connection.set(self.connection)
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        # 步骤 1：无异常则提交，有异常则整体回滚（PRD 11.1 事务边界）
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            _current_connection.reset(self.token)
            self.connection.close()
        # 步骤 2：返回 False 让异常继续向上抛出，由服务层统一转为错误响应
        return False


def transaction() -> _Transaction:
    """开启一个事务块；块内所有写操作共用同一连接（PRD 11.1）。"""
    return _Transaction()


def current_connection() -> "tuple[pymysql.connections.Connection, bool]":
    """返回 (连接, 是否由本次调用创建)。处于事务中时复用事务连接。"""
    # 步骤 1：事务内直接复用，避免跨连接导致事务失效
    existing = _current_connection.get()
    if existing is not None:
        return existing, False
    # 步骤 2：事务外新建连接，并告知调用方需在用后关闭
    return connect(), True


def query(sql: str, params: tuple | list | None = None) -> list[dict]:
    """执行查询并返回全部行（字典形式）。"""
    # 步骤 1：取连接并执行参数化查询——参数化可防注入（PRD 16）
    connection, owned = current_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchall()
    finally:
        # 步骤 2：仅关闭本次调用自建的连接，事务连接交由事务块统一管理
        if owned:
            connection.close()


def query_one(sql: str, params: tuple | list | None = None) -> dict | None:
    """执行查询并返回首行，无结果时返回 None。"""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list | None = None) -> int:
    """执行写语句并返回受影响行数；插入语句返回新主键。"""
    # 步骤 1：取连接并执行参数化写语句
    connection, owned = current_connection()
    try:
        with connection.cursor() as cursor:
            affected = cursor.execute(sql, params or ())
            last_id = cursor.lastrowid
        # 步骤 2：事务外自行提交；事务内交由事务块提交（PRD 11.1）
        if owned:
            connection.commit()
        return last_id if sql.lstrip().upper().startswith("INSERT") else affected
    except Exception:
        if owned:
            connection.rollback()
        raise
    finally:
        if owned:
            connection.close()
