# 批量导入示例

本文件夹用于保存“科研雷达（ResearcherRadar）”的批量导入示例，内容根据 `D:/Desktop/请在当前.docx` 中的研究方向与关键词摘要整理。

## 1. 研究方向批量导入

文件：

```text
01_research_directions_bulk.txt
```

使用位置：

```text
系统管理 -> 研究方向管理 -> 批量添加
```

使用方式：复制文件内容，粘贴到“方向名称”文本框中。系统支持“一行一个研究方向”。

## 2. 关键词批量导入

文件：

```text
02_keywords_*.txt
```

使用位置：

```text
系统管理 -> 关键词管理 -> 批量添加关键词
```

使用方式：

1. 在弹窗中先选择对应研究方向。
2. 分类建议填写：`技术对象`、`方法`、`能源类型`、`评价指标` 或 `系统场景`。
3. 复制对应 `02_keywords_*.txt` 文件内容，粘贴到“关键词”文本框。
4. 建议保持“更新已有”开启，避免重复关键词。

## 3. RSS 源批量导入

文件：

```text
03_rss_sources_sciencedirect_bulk.txt
```

使用位置：

```text
系统管理 -> RSS 源管理 -> 批量添加
```

使用方式：复制文件内容，粘贴到“RSS 源”文本框。推荐统一设置：

```text
出版社：Elsevier
分类：energy
启用：开启
```

## 4. 关键词分类建议

`Keyword.category` 不建议作为主分类使用，主分类应使用“研究方向”。分类更适合当作二级标签：

- `技术对象`：SOFC、PEMFC、ORC、gas turbine
- `方法`：optimization、robust optimization、thermodynamic analysis
- `能源类型`：hydrogen、solar energy、battery
- `评价指标`：exergy、LCA、carbon emission
- `系统场景`：CCHP、distributed energy system、multi-energy system

