"""
元数据标签注入器 - 为文本块自动添加业务标签

功能:
- 从文档内容提取/推断业务标签（部门、类别、生效日期等）
- 关键词提取
- 文档类型识别

用法:
    from metadata_tagger import MetadataTagger

    tagger = MetadataTagger()
    metadata = tagger.extract_tags(text, file_name="员工手册.pdf")
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DocumentTags:
    """文档标签数据结构"""
    # 部门分类
    department: Optional[str] = None      # HR/财务/行政/法务/业务
    sub_department: Optional[str] = None  # 子部门

    # 文档类别
    category: Optional[str] = None        # 出差政策/合同/考勤/报销/招聘/薪酬等
    document_type: Optional[str] = None   # 制度/办法/通知/合同/协议/手册

    # 时间信息
    effective_date: Optional[str] = None  # 生效日期 ISO 8601
    issue_date: Optional[str] = None      # 发布日期
    version: Optional[str] = None         # 版本号

    # 语义标签
    keywords: List[str] = field(default_factory=list)
    entities: Dict[str, str] = field(default_factory=dict)  # 实体：金额/比例/天数等

    # 适用范围
    applicable_roles: List[str] = field(default_factory=list)  # 适用角色
    applicable_depts: List[str] = field(default_factory=list)  # 适用部门


class MetadataTagger:
    """元数据标签提取器"""

    # 部门关键词映射
    DEPARTMENT_KEYWORDS = {
        "HR": ["人力资源", "招聘", "培训", "薪酬", "绩效", "考勤", "员工", "入职", "离职", "劳动合同", "社保", "公积金"],
        "财务": ["财务", "报销", "差旅", "津贴", "补助", "工资", "税务", "发票", "付款", "收款", "预算", "决算"],
        "行政": ["行政", "后勤", "办公", "资产", "采购", "车辆", "会议", "接待", "印章", "档案"],
        "法务": ["法务", "合同", "协议", "诉讼", "仲裁", "合规", "风险", "知识产权", "商标", "专利"],
        "业务": ["业务", "销售", "市场", "客户", "产品", "运营", "项目", "投标", "中标"],
        "IT": ["信息", "技术", "系统", "软件", "硬件", "网络", "安全", "数据", "IT"],
        "研发": ["研发", "开发", "设计", "测试", "创新", "技术", "工程师"],
    }

    # 文档类别关键词
    CATEGORY_KEYWORDS = {
        "出差政策": ["出差", "差旅", "外地", "异地", "交通", "住宿", "差旅费", "报销标准"],
        "合同": ["合同", "协议", "签约", "条款", "甲方", "乙方"],
        "考勤": ["考勤", "打卡", "请假", "休假", "年假", "调休", "旷工", "迟到", "早退"],
        "报销": ["报销", "发票", "费用", "审批", "付款", "补助", "津贴"],
        "招聘": ["招聘", "面试", "录用", "入职", "试用", "转正"],
        "薪酬": ["薪酬", "工资", "薪资", "奖金", "提成", "绩效", "年终奖"],
        "培训": ["培训", "学习", "进修", "考试", "证书", "技能"],
        "福利": ["福利", "保险", "体检", "餐补", "交通补", "住房", "年终奖"],
        "行为规范": ["行为", "规范", "准则", "道德", "职业", "纪律"],
        "安全": ["安全", "消防", "应急", "防护", "生产安全"],
    }

    # 文档类型识别
    DOCUMENT_TYPE_PATTERNS = {
        "制度": [r"制度", r"管理规定", r"管理办法"],
        "办法": [r"办法", r"实施细则"],
        "通知": [r"通知", r"公告", "通告"],
        "手册": [r"手册", r"指南", r"指引"],
        "合同": [r"合同", r"协议"],
        "协议": [r"协议", r"协议书"],
        "规定": [r"规定", r"暂行规定"],
        "流程": [r"流程", r"操作规程", r"作业指导"],
    }

    # 日期模式
    DATE_PATTERNS = [
        r'(\d{4}) 年 (\d{1,2}) 月 (\d{1,2}) 日',
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
        r'(\d{4})/(\d{1,2})/(\d{1,2})',
        r'二〇([零一二三四五六七八九十]+) 年 ([零一二三四五六七八九十]+) 月 ([零一二三四五六七八九十]+) 日',
    ]

    # 生效日期关键词
    EFFECTIVE_DATE_KEYWORDS = [
        "自.*起施行", "自.*起生效", "自.*起执行", "自.*起实施",
        "生效日期", "施行日期", "执行日期", "实施日期",
        "有效期", "有效期限",
    ]

    # 金额模式
    MONEY_PATTERNS = [
        r'人民币\s*(\d+(?:[,，]\d{3})*(?:\.\d+)?)\s*元',
        r'(\d+(?:\.\d+)?)\s*元',
        r'￥(\d+(?:\.\d+)?)',
        r'\$(\d+(?:\.\d+)?)',
    ]

    # 比例模式
    PERCENTAGE_PATTERNS = [
        r'(\d+(?:\.\d+)?)\s*%',
        r'(\d+(?:\.\d+)?)\s*百分之',
        r'(\d+(?:\.\d+)?)\s*成',
    ]

    # 天数模式
    DAYS_PATTERNS = [
        r'(\d+(?:\.\d+)?)\s*天',
        r'(\d+(?:\.\d+)?)\s*日',
        r'(\d+(?:\.\d+)?)\s*个工作日',
    ]

    # 适用角色
    ROLE_PATTERNS = [
        r'(全体员工)',
        r'(正式员工)',
        r'(试用期员工)',
        r'(兼职员工)',
        r'(实习生)',
        r'(管理层)',
        r'(中层干部)',
        r'(高级管理人员)',
        r'(部门[经理总监])',
        r'(主管)',
        r'(HR[BP]?)',
        r'(财务 [人员专干])',
    ]

    def __init__(self):
        """初始化标签提取器"""
        self._compiled_date_patterns = [re.compile(p) for p in self.DATE_PATTERNS]
        self._compiled_effective_keywords = [re.compile(k) for k in self.EFFECTIVE_DATE_KEYWORDS]

    def extract_tags(self, text: str, file_name: Optional[str] = None,
                     existing_metadata: Optional[Dict] = None) -> Dict:
        """
        从文档文本中提取标签

        Args:
            text: 文档文本
            file_name: 文件名（可选，用于辅助判断）
            existing_metadata: 已有元数据（可选，用于合并）

        Returns:
            标签字典
        """
        tags = DocumentTags()

        # 1. 部门识别
        tags.department = self._detect_department(text, file_name)

        # 2. 类别识别
        tags.category = self._detect_category(text, file_name)

        # 3. 文档类型识别
        tags.document_type = self._detect_document_type(text, file_name)

        # 4. 日期提取
        dates = self._extract_dates(text)
        tags.effective_date = dates.get("effective")
        tags.issue_date = dates.get("issue")

        # 5. 关键词提取
        tags.keywords = self._extract_keywords(text)

        # 6. 实体提取（金额、比例、天数等）
        tags.entities = self._extract_entities(text)

        # 7. 适用角色识别
        tags.applicable_roles = self._extract_roles(text)

        # 转换为字典
        result = self._to_dict(tags)

        # 合并已有元数据
        if existing_metadata:
            result = {**existing_metadata, **result}

        return result

    def _detect_department(self, text: str, file_name: Optional[str] = None) -> str:
        """检测文档所属部门"""
        scores = {dept: 0 for dept in self.DEPARTMENT_KEYWORDS.keys()}

        # 检查文件名
        if file_name:
            for dept, keywords in self.DEPARTMENT_KEYWORDS.items():
                for kw in keywords:
                    if kw in file_name:
                        scores[dept] += 5  # 文件名权重更高

        # 检查文档内容（前 2000 字权重更高）
        head_text = text[:2000]
        for dept, keywords in self.DEPARTMENT_KEYWORDS.items():
            for kw in keywords:
                if kw in head_text:
                    scores[dept] += 1

        # 返回得分最高的部门
        max_score = max(scores.values())
        if max_score > 0:
            for dept, score in scores.items():
                if score == max_score:
                    return dept

        return "综合"  # 默认

    def _detect_category(self, text: str, file_name: Optional[str] = None) -> str:
        """检测文档类别"""
        scores = {cat: 0 for cat in self.CATEGORY_KEYWORDS.keys()}

        # 检查文件名
        if file_name:
            for cat, keywords in self.CATEGORY_KEYWORDS.items():
                for kw in keywords:
                    if kw in file_name:
                        scores[cat] += 5

        # 检查文档内容
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text[:3000]:  # 前 3000 字权重更高
                    scores[cat] += 2
                if kw in text:
                    scores[cat] += 1

        max_score = max(scores.values())
        if max_score > 0:
            for cat, score in scores.items():
                if score == max_score:
                    return cat

        return "综合制度"

    def _detect_document_type(self, text: str, file_name: Optional[str] = None) -> str:
        """检测文档类型"""
        # 优先从文件名判断
        if file_name:
            for doc_type, patterns in self.DOCUMENT_TYPE_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, file_name):
                        return doc_type

        # 从内容判断（标题部分）
        head_text = text[:500]
        for doc_type, patterns in self.DOCUMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, head_text):
                    return doc_type

        return "文档"

    def _extract_dates(self, text: str) -> Dict[str, str]:
        """提取文档中的日期"""
        dates = {
            "effective": None,
            "issue": None,
        }

        # 查找所有日期
        found_dates = []
        for pattern in self._compiled_date_patterns:
            for match in pattern.finditer(text[:3000]):  # 在前 3000 字查找
                try:
                    groups = match.groups()
                    if len(groups) == 3:
                        # 处理中文数字
                        year, month, day = self._parse_date_groups(groups)
                        if year and month and day:
                            date_str = f"{year:04d}-{month:02d}-{day:02d}"
                            found_dates.append((match.start(), date_str, match.group()))
                except (ValueError, TypeError):
                    continue

        if not found_dates:
            return dates

        # 按位置排序
        found_dates.sort(key=lambda x: x[0])

        # 第一个日期可能是发布日期
        if found_dates:
            dates["issue"] = found_dates[0][1]

        # 查找生效日期关键词附近的日期
        for kw_pattern in self._compiled_effective_keywords:
            for match in kw_pattern.finditer(text[:3000]):
                # 在关键词前后 100 字范围内查找日期
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end]

                for _, date_str, _ in found_dates:
                    if date_str in context:
                        dates["effective"] = date_str
                        break

        # 如果没找到明确的生效日期，使用最后一个日期
        if not dates["effective"] and found_dates:
            dates["effective"] = found_dates[-1][1]

        return dates

    def _parse_date_groups(self, groups: Tuple) -> Tuple[int, int, int]:
        """解析日期组，处理中文数字"""
        chinese_nums = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

        def parse_chinese(s: str) -> int:
            """解析中文数字"""
            if s.isdigit():
                return int(s)
            # 简单处理：二〇二六 -> 2026
            if "〇" in s:
                return int("".join(str(chinese_nums.get(c, 0)) for c in s))
            # 处理"十三"这样的复合数字
            if len(s) == 2:
                if s[0] == "十":
                    return 10 + chinese_nums.get(s[1], 0)
                elif s[1] == "十":
                    return chinese_nums.get(s[0], 1) * 10
                else:
                    return chinese_nums.get(s[0], 0) * 10 + chinese_nums.get(s[1], 0)
            return chinese_nums.get(s, 0)

        year = parse_chinese(groups[0])
        month = parse_chinese(groups[1])
        day = parse_chinese(groups[2])

        # 年份补全
        if year < 100:
            year += 2000

        return year, month, day

    def _extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """提取关键词"""
        # 简单实现：基于词频统计
        # 实际项目中可使用 jieba 分词 + TF-IDF

        # 移除常见停用词
        stopwords = {
            "的", "了", "和", "是", "在", "就", "都", "而", "及", "与", "或",
            "一个", "一些", "这个", "那个", "这些", "那些",
            "我们", "你们", "他们", "公司", "员工", "人员",
            "应", "应当", "应该", "必须", "不得", "禁止",
        }

        # 简单分词（按标点和空格）
        words = re.split(r'[，。！？；：,\.\!\?;\s\n]+', text)
        words = [w.strip() for w in words if len(w.strip()) > 1]

        # 统计词频
        freq = {}
        for word in words:
            if word not in stopwords:
                freq[word] = freq.get(word, 0) + 1

        # 按频率排序
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)

        # 返回 top_k
        return [word for word, _ in sorted_words[:top_k]]

    def _extract_entities(self, text: str) -> Dict[str, str]:
        """提取实体（金额、比例、天数等）"""
        entities = {}

        # 金额
        for pattern in self.MONEY_PATTERNS:
            for match in re.finditer(pattern, text):
                key = f"金额_{len(entities)}"
                entities[key] = match.group()

        # 比例
        for pattern in self.PERCENTAGE_PATTERNS:
            for match in re.finditer(pattern, text):
                key = f"比例_{len(entities)}"
                entities[key] = match.group()

        # 天数
        for pattern in self.DAYS_PATTERNS:
            for match in re.finditer(pattern, text):
                key = f"天数_{len(entities)}"
                entities[key] = match.group()

        return entities

    def _extract_roles(self, text: str) -> List[str]:
        """提取适用角色"""
        roles = []
        for pattern in self.ROLE_PATTERNS:
            for match in re.finditer(pattern, text):
                role = match.group(1) if match.groups() else match.group()
                if role not in roles:
                    roles.append(role)
        return roles

    def _to_dict(self, tags: DocumentTags) -> Dict:
        """将标签对象转换为字典"""
        return {
            "department": tags.department,
            "category": tags.category,
            "document_type": tags.document_type,
            "effective_date": tags.effective_date,
            "issue_date": tags.issue_date,
            "version": tags.version,
            "keywords": tags.keywords,
            "entities": tags.entities,
            "applicable_roles": tags.applicable_roles,
            "applicable_depts": tags.applicable_depts,
        }


# ==================== 便捷函数 ====================

def extract_document_tags(text: str, file_name: Optional[str] = None) -> Dict:
    """
    便捷函数：提取文档标签

    Args:
        text: 文档文本
        file_name: 文件名

    Returns:
        标签字典
    """
    tagger = MetadataTagger()
    return tagger.extract_tags(text, file_name)


# ==================== 命令行测试 ====================

if __name__ == "__main__":
    test_text = """
# 公司员工差旅费管理办法

## 第一章 总则

第一条 为规范公司差旅费管理，合理控制费用支出，根据国家有关规定，结合公司实际情况，制定本办法。

第二条 本办法适用于公司全体员工因公出差的费用管理。

第三条 差旅费包括：城市间交通费、住宿费、伙食补助费、市内交通费。

## 第二章 出差审批

第四条 员工出差应提前填写《出差申请单》，经部门负责人批准后方可出行。

第五条 出差天数一般不超过 7 天，特殊情况需延长出差时间的，应提前报批。

## 第三章 费用标准

第六条 住宿费标准：
（一）总经理及以上级别：实报实销
（二）部门经理：不超过 500 元/天
（三）一般员工：不超过 300 元/天

第七条 伙食补助费：每人每天 100 元。

第八条 市内交通费：每人每天 50 元，凭发票报销。

本办法自 2026 年 1 月 1 日起施行。
"""

    tagger = MetadataTagger()
    tags = tagger.extract_tags(test_text, file_name="差旅费管理办法.pdf")

    print("\n=== 元数据标签提取结果 ===\n")
    print(f"部门：{tags['department']}")
    print(f"类别：{tags['category']}")
    print(f"文档类型：{tags['document_type']}")
    print(f"生效日期：{tags['effective_date']}")
    print(f"关键词：{', '.join(tags['keywords'][:5])}")
    print(f"实体：{tags['entities']}")
    print(f"适用角色：{tags['applicable_roles']}")