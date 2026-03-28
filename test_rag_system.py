"""
混合检索系统测试脚本

测试内容:
1. Chunker 递归层级切片
2. MetadataTagger 元数据提取
3. HybridRetriever 混合检索

用法:
    python test_rag_system.py
"""

import os
import sys

# 设置 UTF-8 编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def test_chunker():
    """测试递归层级切片器"""
    print("\n" + "=" * 60)
    print("测试 1: RecursiveChunker 递归层级切片")
    print("=" * 60)

    from chunker import RecursiveChunker

    test_text = """
# 第一章 总则

第一条 为了规范公司员工管理，制定本手册。

第二条 本手册适用于公司全体员工。

# 第二章 招聘与录用

## 第一节 招聘流程

第三条 公司招聘遵循公开、公平、公正的原则。

第四条 招聘流程：
（一）部门提出用人需求
（二）人力资源部审核并发布招聘信息
（三）简历筛选和初试
（四）复试和背景调查
（五）发放录用通知

## 第二节 入职手续

第五条 新员工入职需提供以下材料：
1. 身份证复印件
2. 学历学位证明复印件
3. 前一家公司离职证明

# 第三章 考勤管理

## 第一节 工作时间

第六条 公司实行标准工时制，工作时间为周一至周五。
"""

    chunker = RecursiveChunker(chunk_size=200, overlap_ratio=0.1)
    chunks = chunker.split_recursive(test_text)

    print(f"\n输入文本长度：{len(test_text)} 字符")
    print(f"切分结果：共 {len(chunks)} 个块\n")

    for i, chunk in enumerate(chunks):
        print(f"[块 {i + 1}]")
        print(f"  标题：{chunk.section_title}")
        print(f"  层级：{chunk.heading_level}")
        print(f"  路径：{chunk.hierarchy_path}")
        print(f"  字数：{len(chunk.text)}")
        print()

    return len(chunks) > 0


def test_metadata_tagger():
    """测试元数据标签提取器"""
    print("\n" + "=" * 60)
    print("测试 2: MetadataTagger 元数据提取")
    print("=" * 60)

    from metadata_tagger import MetadataTagger

    test_text = """
# 公司员工差旅费管理办法

## 第一章 总则

第一条 为规范公司差旅费管理，合理控制费用支出，根据国家有关规定，结合公司实际情况，制定本办法。

第二条 本办法适用于公司全体员工因公出差的费用管理。

第三条 差旅费包括：城市间交通费、住宿费、伙食补助费、市内交通费。

## 第二章 费用标准

第四条 住宿费标准：
（一）总经理及以上级别：实报实销
（二）部门经理：不超过 500 元/天
（三）一般员工：不超过 300 元/天

第五条 伙食补助费：每人每天 100 元。

第六条 市内交通费：每人每天 50 元，凭发票报销。

本办法自 2026 年 1 月 1 日起施行。
"""

    tagger = MetadataTagger()
    tags = tagger.extract_tags(test_text, file_name="差旅费管理办法.pdf")

    print("\n元数据标签提取结果:")
    print(f"  部门：{tags['department']}")
    print(f"  类别：{tags['category']}")
    print(f"  文档类型：{tags['document_type']}")
    print(f"  生效日期：{tags['effective_date']}")
    print(f"  关键词：{', '.join(tags['keywords'][:5])}")
    print(f"  实体：{tags['entities']}")
    print(f"  适用角色：{tags['applicable_roles']}")

    return tags['department'] is not None


def test_hybrid_retriever():
    """测试混合检索器"""
    print("\n" + "=" * 60)
    print("测试 3: HybridRetriever 混合检索")
    print("=" * 60)

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("\n[跳过] 未设置 DASHSCOPE_API_KEY 环境变量")
        return True

    try:
        from retriever import HybridRetriever, BM25Retriever

        # 测试 BM25 检索器
        print("\n测试 BM25 检索器:")
        documents = [
            "公司员工出差报销标准包括交通费、住宿费、伙食补助费",
            "差旅费管理办法规定总经理级别实报实销",
            "员工请假需提前申请，病假应及时通知部门主管",
            "劳动合同自用工之日起一个月内签订",
        ]

        bm25 = BM25Retriever(documents=documents, language="zh")
        results = bm25.search("出差报销标准", k=3)

        print(f"  查询：'出差报销标准'")
        print(f"  检索到 {len(results)} 条结果")
        for i, result in enumerate(results):
            print(f"  [{i + 1}] 分数：{result.keyword_score:.4f} - {result.text[:50]}...")

        # 测试混合检索器（需要 ChromaDB 中有数据）
        print("\n测试混合检索器（需要 ChromaDB 数据）:")
        retriever = HybridRetriever(
            chroma_path="./chroma_db",
            collection_name="legal_docs",
            api_key=api_key,
            use_rerank=False,
            embedding_model="text-embedding-v3"  # 使用 v3 匹配现有 ChromaDB 维度
        )

        # 检查是否有数据
        collection = retriever.vector_retriever._get_collection()
        count = collection.count()

        if count > 0:
            print(f"  ChromaDB 中有 {count} 条文档")

            results = retriever.retrieve("出差报销标准", top_k=3)
            print(f"  检索到 {len(results)} 条结果")

            for i, result in enumerate(results):
                print(f"  [{i + 1}] 分数：{result['score']:.4f}")
                print(f"      来源：{result['source']}")
                print(f"      文件：{result['metadata'].get('file_name', '未知')}")
                print(f"      内容：{result['text'][:50]}...")
        else:
            print("  [跳过] ChromaDB 为空，先运行 ingest_enhanced.py 导入数据")

        return True

    except Exception as e:
        print(f"  [错误] {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("RAG 系统优化 - 模块测试")
    print("=" * 60)

    results = {
        "chunker": test_chunker(),
        "metadata_tagger": test_metadata_tagger(),
        "hybrid_retriever": test_hybrid_retriever(),
    }

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"\n通过：{passed}/{total}")

    for name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")

    if passed == total:
        print("\n所有测试通过！")
        return 0
    else:
        print("\n部分测试失败，请检查错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
