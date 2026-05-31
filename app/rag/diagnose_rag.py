import asyncio
from app.rag.vector_store import VectorStoreService
from app.utils.logger_handler import logger


async def diagnose():
    """诊断RAG系统的数据状态"""
    logger.info("=" * 60)
    logger.info("RAG 系统诊断工具")
    logger.info("=" * 60)

    # 1. 初始化向量存储服务
    vector_store = VectorStoreService()

    # 2. 检查所有用户的文档
    logger.info("\n【1】检查所有用户的文档:")
    all_docs = await vector_store.get_user_documents()
    if all_docs:
        for doc in all_docs:
            logger.info(f"  - 文件名: {doc['filename']}")
            logger.info(f"    用户ID: {doc['user_id']}")
            logger.info(f"    切片数: {doc['chunk_count']}")
            logger.info(f"    预览: {doc['preview'][:50]}...")
            logger.info()
    else:
        logger.error("向量数据库中没有任何文档！")

    # 3. 检查特定用户的文档
    test_user_id = "eiXLpAR5PsfGBoMJvjXV34"
    print(f"\n【2】检查用户 {test_user_id} 的文档:")
    user_docs = await vector_store.get_user_documents(user_id=test_user_id)
    if user_docs:
        print(f"  ✅ 找到 {len(user_docs)} 个文件")
        for doc in user_docs:
            print(f"  - {doc['filename']} ({doc['chunk_count']} 个切片)")
    else:
        print(f"  ❌ 用户 {test_user_id} 没有文档")

    # 4. 检查 MD5 记录
    print(f"\n【3】检查用户 {test_user_id} 的MD5记录:")
    md5_records = await vector_store.get_all_md5_records(test_user_id)
    if md5_records:
        print(f"  ✅ 找到 {len(md5_records)} 条MD5记录")
        for record in md5_records[:5]:  # 只显示前5条
            print(f"  - {record}")
    else:
        print(f"  ❌ 用户 {test_user_id} 没有MD5记录")

    # 5. 测试检索
    print(f"\n【4】测试检索功能:")
    from app.rag.rag_service import RagService

    rag_service = RagService(user_id=test_user_id)
    query = "如何判断扫拖一体机器人是否需要更换新机？"
    print(f"  查询: {query}")

    documents = await rag_service.retrieve_document(query)
    print(f"  检索结果: {len(documents)} 个文档")

    if documents:
        for i, doc in enumerate(documents[:3], 1):
            print(f"\n  文档 {i}:")
            print(f"  内容预览: {doc.page_content[:100]}...")
            print(f"  来源: {doc.metadata.get('original_filename', 'unknown')}")

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(diagnose())
