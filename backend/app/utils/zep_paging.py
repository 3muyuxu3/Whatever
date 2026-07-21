"""Zep API 分页处理工具。

Zep 的节点/边查询接口通常按游标（cursor）或页码分页，这里提供通用聚合函数。
"""

from .logger import get_logger

logger = get_logger("zep_paging")


def paginate(fetch_page, page_size: int = 100, max_pages: int = 1000) -> list:
    """通用分页聚合。

    :param fetch_page: 回调函数 (cursor, page_size) -> (items, next_cursor)
                       当没有更多数据时应返回空列表和 falsy 的游标。
    :param page_size:  每页数量
    :param max_pages:  最大翻页次数（防止死循环）
    :return: 聚合后的全部条目列表
    """
    results: list = []
    cursor = None
    for _ in range(max_pages):
        items, cursor = fetch_page(cursor, page_size)
        if not items:
            break
        results.extend(items)
        if not cursor:
            break
    return results
