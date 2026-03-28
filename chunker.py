"""
递归层级切片器 - 专用于中文政策文档

功能:
- 按中文政策文档层级递归切分（章→节→条→款→项）
- 支持可控 overlap（重叠度），避免上下文丢失
- 语义边界检测，在句子/段落边界处切分

用法:
    from chunker import RecursiveChunker

    chunker = RecursiveChunker(chunk_size=500, overlap_ratio=0.1)
    chunks = chunker.split_recursive(text)
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """文本块数据结构"""
    text: str                           # 块内容
    section_title: str                  # 章节标题
    heading_level: int                  # 标题层级 (0=无标题，1=章，2=节，3=条，4=款)
    hierarchy_path: str = ""            # 层级路径：第一章 > 第三节>第五条
    start_offset: int = 0               # 在原文中的起始位置
    end_offset: int = 0                 # 在原文中的结束位置
    page_num: int = 1                   # 所属页码
    page_range: str = ""                # 页码范围：如 "3-5" 表示跨第 3-5 页
    keywords: List[str] = field(default_factory=list)  # 关键词
    metadata: Dict = field(default_factory=dict)       # 额外元数据


class RecursiveChunker:
    """递归层级切片器"""

    # 中文层级标记模式
    HIERARCHY_PATTERNS = {
        1: [  # 第一级：编/部分
            r'^第 [零一二三四五六七八九十百千]+[编部部分篇]',
            r'^[编部部分篇][零一二三四五六七八九十百千]+[、：:]',
        ],
        2: [  # 第二级：章
            r'^第 [零一二三四五六七八九十百千]+章',
            r'^章[零一二三四五六七八九十百千]+[、：:]',
        ],
        3: [  # 第三级：节
            r'^第 [零一二三四五六七八九十百千]+节',
            r'^节[零一二三四五六七八九十百千]+[、：:]',
        ],
        4: [  # 第四级：条
            r'^第 [零一二三四五六七八九十百千]+条',
            r'^(?:第 [零一二三四五六七八九十]+条|第\d+ 条)',
        ],
        5: [  # 第五级：款/项
            r'^[（(][零一二三四五六七八九十百]+[)）]',
            r'^[（(]\d+[)）]',
            r'^[零一二三四五六七八九十百]+[、：:]',
            r'^\d+[、．.]',
        ],
    }

    # 层级名称映射
    LEVEL_NAMES = {
        1: "部分",
        2: "章",
        3: "节",
        4: "条",
        5: "款",
    }

    def __init__(self, chunk_size: int = 500, overlap_ratio: float = 0.1,
                 min_chunk_size: int = 100):
        """
        初始化切片器

        Args:
            chunk_size: 目标块大小（字符数）
            overlap_ratio: 重叠比例 (0.1 = 10% 重叠)
            min_chunk_size: 最小块大小，小于此值的块会尝试合并
        """
        self.chunk_size = chunk_size
        self.overlap_ratio = overlap_ratio
        self.min_chunk_size = min_chunk_size
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[int, List[re.Pattern]]:
        """预编译正则表达式"""
        compiled = {}
        for level, patterns in self.HIERARCHY_PATTERNS.items():
            compiled[level] = [
                re.compile(pattern, re.MULTILINE)
                for pattern in patterns
            ]
        return compiled

    def _detect_hierarchy_level(self, line: str) -> int:
        """
        检测行文本的层级级别

        Returns:
            层级级别 (1-5)，0 表示不是层级标题
        """
        line = line.strip()
        if not line:
            return 0

        for level in sorted(self._compiled_patterns.keys()):
            for pattern in self._compiled_patterns[level]:
                if pattern.match(line):
                    return level
        return 0

    def _extract_hierarchy_title(self, line: str) -> str:
        """从行文本中提取层级标题"""
        line = line.strip()
        # 移除末尾的标点
        title = re.sub(r'[、：:\s]+$', '', line)
        return title

    def _parse_document_structure(self, text: str) -> List[Dict]:
        """
        解析文档的层级结构

        Returns:
            结构化列表，每项包含：{level, title, start, end, content}
        """
        lines = text.split('\n')
        structure = []
        current_pos = 0

        # 默认根节点
        root = {
            "level": 0,
            "title": "文档根节点",
            "start": 0,
            "end": len(text),
            "content": text,
            "children": []
        }

        # 栈：用于跟踪当前层级的父节点
        stack = [(0, root)]  # (level, node)

        current_section = {
            "level": 0,
            "title": "文档概述",
            "start": 0,
            "content_lines": []
        }

        sections = []

        for i, line in enumerate(lines):
            level = self._detect_hierarchy_level(line)

            if level > 0:
                # 保存之前的章节
                if current_section["content_lines"]:
                    content = '\n'.join(current_section["content_lines"])
                    current_section["end"] = current_pos
                    current_section["content"] = content
                    sections.append(current_section)

                # 创建新章节
                title = self._extract_hierarchy_title(line)
                current_section = {
                    "level": level,
                    "title": title,
                    "start": current_pos,
                    "content_lines": [line]
                }
            else:
                if line.strip():  # 非空行
                    current_section["content_lines"].append(line)

            current_pos += len(line) + 1  # +1 for newline

        # 处理最后一个章节
        if current_section["content_lines"]:
            content = '\n'.join(current_section["content_lines"])
            current_section["end"] = current_pos
            current_section["content"] = content
            sections.append(current_section)

        return sections

    def _split_by_semantic_boundaries(self, text: str, max_length: int) -> List[str]:
        """
        在语义边界处切分文本

        优先级：段落 > 句子 > 短语
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        remaining = text

        while len(remaining) > max_length:
            # 尝试在段落边界切分
            split_pos = self._find_split_position(remaining, max_length)

            if split_pos > 0:
                chunk = remaining[:split_pos].strip()
                if chunk:
                    chunks.append(chunk)
                remaining = remaining[split_pos:].strip()
            else:
                # 无法找到合适边界，强制切分
                chunks.append(remaining[:max_length])
                remaining = remaining[max_length:]

        if remaining:
            chunks.append(remaining)

        return chunks

    def _find_split_position(self, text: str, target_pos: int) -> int:
        """
        找到最佳切分位置（在语义边界处）

        搜索范围：target_pos ± 20% target_pos
        """
        margin = int(target_pos * 0.2)
        start = max(0, target_pos - margin)
        end = min(len(text), target_pos + margin)

        search_range = text[start:end]

        # 优先级 1: 段落边界 (\n\n)
        for sep in ['\n\n', '\n', '。', '！', '？', '.', '!', '?']:
            pos = search_range.rfind(sep)
            if pos != -1:
                return start + pos + len(sep)

        # 未找到边界，返回目标位置
        return target_pos

    def _add_overlap(self, chunks: List[str], overlap_chars: int) -> List[str]:
        """
        为 chunks 添加重叠内容

        Args:
            chunks: 原始分块列表
            overlap_chars: 重叠字符数

        Returns:
            带重叠的分块列表
        """
        if not chunks or overlap_chars <= 0:
            return chunks

        result = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                result.append(chunk)
            else:
                # 从前一块末尾获取重叠内容
                prev_chunk = chunks[i - 1]
                overlap_text = prev_chunk[-overlap_chars:] if len(prev_chunk) > overlap_chars else prev_chunk

                # 在语义边界处截断重叠部分
                if len(overlap_text) > overlap_chars // 2:
                    overlap_text = self._trim_to_boundary(overlap_text, overlap_chars)

                # 合并重叠内容
                new_chunk = overlap_text + chunk
                result.append(new_chunk)

        return result

    def _trim_to_boundary(self, text: str, max_length: int) -> str:
        """将文本修剪到最近的语义边界"""
        if len(text) <= max_length:
            return text

        # 在句子边界处截断
        for sep in ['。', '！', '？', '.', '!', '?', '\n']:
            pos = text[:max_length].rfind(sep)
            if pos != -1:
                return text[:pos + 1]

        return text[:max_length]

    def _calculate_page_range(self, start: int, end: int,
                              page_map: Optional[List[Tuple[int, int, int]]]) -> Tuple[int, str]:
        """
        根据 offset 计算 chunk 所属的页码

        Args:
            start: chunk 在原文中的起始 offset
            end: chunk 在原文中的结束 offset
            page_map: 页码映射列表，每项为 (page_num, start_pos, end_pos)

        Returns:
            (主页码，页码范围字符串如 "3" 或 "3-5")
        """
        if not page_map:
            return 1, ""

        # 找到 start 和 end 所在的页码
        start_page = None
        end_page = None

        for page_num, page_start, page_end in page_map:
            if page_start <= start < page_end:
                start_page = page_num
            if page_start < end <= page_end:
                end_page = page_num
            # 优化：如果已经找到两端页码，提前退出
            if start_page and end_page:
                break

        # 如果找不到，使用第一页
        if start_page is None:
            start_page = 1
        if end_page is None:
            end_page = start_page

        # 构建页码范围
        if start_page == end_page:
            return start_page, str(start_page)
        else:
            return start_page, f"{start_page}-{end_page}"

    def split_recursive(self, text: str,
                        hierarchy_levels: Optional[List[int]] = None,
                        page_map: Optional[List[Tuple[int, int, int]]] = None) -> List[Chunk]:
        """
        递归层级切分

        Args:
            text: 待切分的文本
            hierarchy_levels: 要考虑的层级列表，默认 [1,2,3,4,5]
            page_map: 页码映射列表，每项为 (page_num, start_pos, end_pos)，
                      用于根据 offset 计算 chunk 所属的页码

        Returns:
            Chunk 对象列表
        """
        if hierarchy_levels is None:
            hierarchy_levels = [1, 2, 3, 4, 5]

        # Step 1: 解析文档结构
        sections = self._parse_document_structure(text)

        # Step 2: 按层级处理每个章节
        chunks = []
        current_path = []

        for section in sections:
            level = section["level"]
            title = section["title"]
            content = section.get("content", "")

            # 更新层级路径
            # 找到当前层级在路径中的位置
            while current_path and current_path[-1][0] >= level:
                current_path.pop()
            current_path.append((level, title))
            hierarchy_path = " > ".join([t for _, t in current_path])

            # 计算 section 的页码
            page_num, page_range = self._calculate_page_range(
                section["start"], section["end"], page_map
            )

            # Step 3: 判断是否需要进一步切分
            if len(content) > self.chunk_size * 1.5:
                # 内容过大，需要进一步切分
                sub_chunks = self._split_by_semantic_boundaries(
                    content, self.chunk_size
                )

                for i, sub_chunk in enumerate(sub_chunks):
                    # 计算 sub_chunk 的页码
                    sub_start = section["start"] + sum(len(c) for c in sub_chunks[:i])
                    sub_end = sub_start + len(sub_chunk)
                    sub_page_num, sub_page_range = self._calculate_page_range(
                        sub_start, sub_end, page_map
                    )

                    chunk = Chunk(
                        text=sub_chunk,
                        section_title=title,
                        heading_level=level,
                        hierarchy_path=hierarchy_path,
                        start_offset=section["start"],
                        end_offset=section["end"],
                        page_num=sub_page_num,
                        page_range=sub_page_range,
                        metadata={"sub_chunk_id": i, "total_sub_chunks": len(sub_chunks)}
                    )
                    chunks.append(chunk)
            else:
                # 内容合适，直接添加
                chunk = Chunk(
                    text=content,
                    section_title=title,
                    heading_level=level,
                    hierarchy_path=hierarchy_path,
                    start_offset=section["start"],
                    end_offset=section["end"],
                    page_num=page_num,
                    page_range=page_range,
                )
                chunks.append(chunk)

        # Step 4: 添加 overlap
        overlap_chars = int(self.chunk_size * self.overlap_ratio)
        if overlap_chars > 0:
            chunks_with_overlap = []
            texts = [c.text for c in chunks]
            overlapped_texts = self._add_overlap(texts, overlap_chars)

            for i, chunk in enumerate(chunks):
                chunk.text = overlapped_texts[i]
                chunks_with_overlap.append(chunk)
            chunks = chunks_with_overlap

        # Step 5: 合并过小的块
        chunks = self._merge_small_chunks(chunks)

        return chunks

    def _merge_small_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """合并连续的小块"""
        if not chunks:
            return chunks

        result = []
        current_group = [chunks[0]]
        current_size = len(chunks[0].text)

        for chunk in chunks[1:]:
            chunk_size = len(chunk.text)

            # 如果块太小且与当前组层级相同，尝试合并
            if chunk_size < self.min_chunk_size and current_size + chunk_size < self.chunk_size * 1.2:
                if chunk.heading_level == current_group[-1].heading_level:
                    # 合并
                    current_group.append(chunk)
                    current_size += chunk_size
                else:
                    # 层级不同，保存当前组并开始新组
                    result.extend(self._consolidate_group(current_group))
                    current_group = [chunk]
                    current_size = chunk_size
            else:
                # 块足够大，保存当前组并开始新组
                result.extend(self._consolidate_group(current_group))
                current_group = [chunk]
                current_size = chunk_size

        # 处理最后一组
        result.extend(self._consolidate_group(current_group))

        return result

    def _consolidate_group(self, group: List[Chunk]) -> List[Chunk]:
        """ consolidation 一组块 """
        if len(group) == 1:
            return group

        # 合并为一个块
        merged_text = '\n\n'.join([c.text for c in group])
        first = group[0]

        return [Chunk(
            text=merged_text,
            section_title=first.section_title,
            heading_level=first.heading_level,
            hierarchy_path=first.hierarchy_path,
            start_offset=first.start_offset,
            end_offset=group[-1].end_offset,
            metadata={"merged_from": len(group), "merged_chunk_ids": [i for i in range(len(group))]}
        )]

    def split_by_fixed_size(self, text: str,
                            chunk_size: Optional[int] = None,
                            overlap_ratio: Optional[float] = None) -> List[Chunk]:
        """
        按固定大小切分（备用方案）

        Args:
            text: 待切分的文本
            chunk_size: 块大小（覆盖默认值）
            overlap_ratio: 重叠比例（覆盖默认值）

        Returns:
            Chunk 对象列表
        """
        chunk_size = chunk_size or self.chunk_size
        overlap_ratio = overlap_ratio or self.overlap_ratio
        overlap_chars = int(chunk_size * overlap_ratio)

        chunks = self._split_by_semantic_boundaries(text, chunk_size)

        # 添加 overlap
        if overlap_chars > 0:
            chunks = self._add_overlap(chunks, overlap_chars)

        # 转换为 Chunk 对象
        result = []
        current_pos = 0
        for i, chunk_text in enumerate(chunks):
            chunk = Chunk(
                text=chunk_text,
                section_title="文档片段",
                heading_level=0,
                hierarchy_path="文档片段",
                start_offset=current_pos,
                end_offset=current_pos + len(chunk_text),
                metadata={"chunk_index": i}
            )
            result.append(chunk)
            current_pos += len(chunk_text)

        return result


# ==================== 便捷函数 ====================

def split_document(text: str, chunk_size: int = 500, overlap_ratio: float = 0.1) -> List[Dict]:
    """
    便捷函数：切分文档

    Args:
        text: 待切分的文本
        chunk_size: 目标块大小
        overlap_ratio: 重叠比例

    Returns:
        字典列表，每项包含：{text, section_title, heading_level, hierarchy_path, ...}
    """
    chunker = RecursiveChunker(chunk_size=chunk_size, overlap_ratio=overlap_ratio)
    chunks = chunker.split_recursive(text)

    return [
        {
            "text": chunk.text,
            "section_title": chunk.section_title,
            "heading_level": chunk.heading_level,
            "hierarchy_path": chunk.hierarchy_path,
            "start_offset": chunk.start_offset,
            "end_offset": chunk.end_offset,
            "keywords": chunk.keywords,
            "metadata": chunk.metadata,
        }
        for chunk in chunks
    ]


# ==================== 命令行测试 ====================

if __name__ == "__main__":
    # 测试用例
    test_text = """
# 第一章 总则

第一条 为了规范公司员工管理，维护公司和员工的合法权益，根据国家相关法律法规，结合公司实际情况，制定本手册。

第二条 本手册适用于公司全体员工。

第三条 公司秉持"以人为本、诚信经营"的理念，致力于为员工创造良好的工作环境和发展平台。

# 第二章 招聘与录用

## 第一节 招聘流程

第四条 公司招聘遵循"公开、公平、公正"的原则，择优录用。

第五条 招聘流程：
（一）部门提出用人需求
（二）人力资源部审核并发布招聘信息
（三）简历筛选和初试
（四）复试和背景调查
（五）发放录用通知

## 第二节 入职手续

第六条 新员工入职需提供以下材料：
1. 身份证复印件
2. 学历学位证明复印件
3. 前一家公司离职证明
4. 体检报告
5. 一寸免冠照片 2 张

第七条 公司自用工之日起一个月内与员工签订书面劳动合同。

# 第三章 考勤管理

## 第一节 工作时间

第八条 公司实行标准工时制，工作时间为：
周一至周五：上午 9:00-12:00，下午 13:00-18:00

第九条 员工每日工作 8 小时，每周工作 40 小时。

## 第二节 请假制度

第十条 员工请假分为：
（一）事假：因私事需要请假的，应提前 1 天申请
（二）病假：因病需要请假的，应及时通知部门主管
（三）年假：工作满 1 年的员工，每年享有 5 天带薪年假
（四）婚假：符合法定结婚年龄的员工，享有 3 天婚假
（五）产假：符合计划生育政策的女员工，享有 98 天产假
"""

    chunker = RecursiveChunker(chunk_size=300, overlap_ratio=0.1)
    chunks = chunker.split_recursive(test_text)

    print(f"\n切分结果：共 {len(chunks)} 个块\n")
    print("=" * 60)

    for i, chunk in enumerate(chunks):
        print(f"\n【块 {i + 1}】")
        print(f"  标题：{chunk.section_title}")
        print(f"  层级：{chunk.heading_level}")
        print(f"  路径：{chunk.hierarchy_path}")
        print(f"  字数：{len(chunk.text)}")
        print(f"  内容预览：{chunk.text[:100]}...")