---
title: 默认模块
language_tabs:
  - shell: Shell
  - http: HTTP
  - javascript: JavaScript
  - ruby: Ruby
  - python: Python
  - php: PHP
  - java: Java
  - go: Go
toc_footers: []
includes: []
search: true
code_clipboard: true
highlight_theme: darkula
headingLevel: 2
generator: "@tarslib/widdershins v4.0.30"

---

# JUMO-api-service

## GET 获取任务信息

GET /task-status/{task_id}

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|task_id|path|string| yes |在请求分析任务的时候返回的任务ID|

> Response Examples

```json
{
  "task_id": "01K0E8CP0P",
  "status": "PROCESSING",
  "message": "任务正在处理"
}
```

```json
{
  "task_id": "01K0E8BRGW",
  "status": "COMPLETED",
  "result": {
    "markdown": "01K0E8BRGW/deepseek.md",
    "content_list": "01K0E8BRGW/deepseek_content_list.json",
    "middle_json": "01K0E8BRGW/deepseek_middle.json",
    "images": [
      "01K0E8BRGW/images/ae3b280372957204b1a8a975041a664354462da1919e0ac34ee8926bbcf1ea3b.jpg",
      "01K0E8BRGW/images/e55e41c9be482eec24656880d517cffb3c64a1a5f3caee5055d44424eae5e77f.jpg"
    ],
    "splitted_markdown": "01K0E8BRGW/deepseek_splitted.md"
  }
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» task_id|string|true|none||任务ID|
|» status|string|true|none||状态|
|» result|object|true|none||none|
|»» markdown|string|true|none||生成的markdown文件的url|
|»» content_list|string|true|none||content_list的url|
|»» middle_json|string|true|none||middle_json的url|
|»» images|[string]|true|none||文章中所使用的图片的url|
|»» splitted_markdown|string|true|none||切分过的markdown文件url|

## POST 分析文件请求

POST /analyze-pdf

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|pdf_path|query|string| yes |文件路径（对应bucket_name指定的bucket中的路径）|
|bucket_name|query|string| yes |读取文件的bucket|
|output_bucket|query|string| yes |输出结果文件的bucket|
|ocr_enabled|query|string| yes |是否开启ocr，如果关闭则传false|
|table_enabled|query|string| yes |是否开启表格识别,如果关闭则传false|
|ocr_lang|query|string| yes |    CH = "ch"|

#### Description

**ocr_lang**:     CH = "ch"
    CH_SERVER = "ch_server"
    CH_LITE = "ch_lite"
    EN = "en"
    KOREAN = "korean"
    JAPAN = "japan"
    CHINESE_CHT = "chinese_cht"
    TA = "ta"
    TE = "te"
    KA = "ka"

> Response Examples

> 200 Response

```json
{
  "task_id": "01K0E8BRGW",
  "status": "PROCESSING",
  "message": "任务正在处理"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» task_id|string|true|none||任务ID|
|» status|string|true|none||任务状态|
|» message|string|true|none||任务状态信息描述|

## POST 上传文件并分析

POST /upload-and-analyze-pdf

通过这个接口可以直接传文件进行解析，服务将把文件自动存储到默认bucket，仅用于测试。

> Body Parameters

```yaml
file: ""

```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|output_bucket|query|string| no |none|
|ocr_enabled|query|string| no |none|
|table_enabled|query|string| no |none|
|ocr_lang|query|string| no |none|
|body|body|object| no |none|
|» file|body|string(binary)| no |上传要解析的文件，支持的类型包括ms office支持的类型、图片和txt文档|

> Response Examples

> 200 Response

```json
{
  "task_id": "01K0E8BRGW",
  "status": "PROCESSING",
  "message": "任务正在处理"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» task_id|string|true|none||任务ID|
|» status|string|true|none||任务状态|
|» message|string|true|none||返回任务处理的状态信息|

## GET 下载任务文件

GET /download-task-files/{task_id}

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|task_id|path|string| yes |使用任务ID指定要下载的文件信息|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## POST 批量获取任务信息

POST /batch-task-status

> Body Parameters

```json
[
  "01K0X7GBG7",
  "01K0R8XFDT"
]
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|Content-Type|header|string| yes |none|
|body|body|array[string]| no |none|

> Response Examples

> 200 Response

```json
[
  {
    "task_id": "01K0X7GBG7",
    "status": "COMPLETED",
    "result": {
      "markdown": "01K0X7GBG7/IEC 61400-50-2-2022 Wind energy generation systems – Part 50-2 Wind measurement – Application of ground-mounted remote sensing technology.md",
      "content_list": "01K0X7GBG7/IEC 61400-50-2-2022 Wind energy generation systems – Part 50-2 Wind measurement – Application of ground-mounted remote sensing technology_content_list.json",
      "middle_json": "01K0X7GBG7/IEC 61400-50-2-2022 Wind energy generation systems – Part 50-2 Wind measurement – Application of ground-mounted remote sensing technology_middle.json",
      "images": [
        "01K0X7GBG7/images/7654abcd8a8288fc3208fd9a6b35e3406e454253ef665a527c3a959ec232dfe9.jpg",
        "01K0X7GBG7/images/8c477680f9a7994dc3fd157a17f70f8bed9316df4509e2c1ef1d838e7010849a.jpg"
      ],
      "splitted_markdown": "01K0X7GBG7/IEC 61400-50-2-2022 Wind energy generation systems – Part 50-2 Wind measurement – Application of ground-mounted remote sensing technology_splitted.md"
    }
  },
  {
    "task_id": "01K0R8XFDT",
    "status": "COMPLETED",
    "result": {
      "markdown": "01K0R8XFDT/IEC 61400-1-2019 Wind energy generation systems–Part1：Design requirements.md",
      "content_list": "01K0R8XFDT/IEC 61400-1-2019 Wind energy generation systems–Part1：Design requirements_content_list.json",
      "middle_json": "01K0R8XFDT/IEC 61400-1-2019 Wind energy generation systems–Part1：Design requirements_middle.json",
      "images": [
        "01K0R8XFDT/images/f109b61cde53f015456b17f2f591501aedb79409a0d5699b90cfe0f25430a3d9.jpg",
        "01K0R8XFDT/images/81ba22fa31c2e14ec3fee2beb2ec130f14bb4071bc73c2344629de242da6bfa5.jpg"
      ],
      "splitted_markdown": "01K0R8XFDT/IEC 61400-1-2019 Wind energy generation systems–Part1：Design requirements_splitted.md"
    }
  }
]
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» task_id|string|true|none||任务ID|
|» status|string|true|none||任务状态|
|» result|object|true|none||任务完成后生成的文件|
|»» markdown|string|true|none||markdown文件的url|
|»» content_list|string|true|none||content_list的url|
|»» middle_json|string|true|none||middle_json的url|
|»» images|[string]|true|none||解析出的markdown文件中所用到的图片|
|»» splitted_markdown|string|true|none||经过切分的markdown文件|

## POST word和excel切分接口

POST /analyze-office-file

这个接口用于实时的解析请求，接口会同步返回解析结果，而不是生成一个任务ID。这里支持的格式为MS office支持的文件类型。

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|file_path|query|string| no |文件路径|
|bucket_name|query|string| no |文件在oss中存储的bucket|
|output_bucket|query|string| no |指定解析完成后的文件输出到哪个bucket|
|processing_type|query|string| no |处理方式|
|max_heading_chunk_size|query|integer| no |最大标题块大小|
|fallback_chunk_size|query|integer| no |回退块大小|

> Response Examples

> 200 Response

```json
{
  "status": "success",
  "message": "文件分析完成",
  "data": {
    "markdown_url": "documents/report_2024/report_2024.md",
    "markdown_content": "# 年度报告\n\n## 概述\n\n本报告总结了2024年的主要业务成果...\n\n### 财务数据\n\n| 项目 | 金额 |\n|------|------|\n| 收入 | 1000万 |\n| 支出 | 800万 |\n\n## 结论\n\n通过本年度的努力，公司实现了稳步增长。",
    "images": null
  }
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» status|string|true|none||解析任务的状态|
|» message|string|true|none||任务信息|
|» data|object|true|none||none|
|»» markdown_url|string|true|none||生成的markdown文件的url|
|»» markdown_content|string|true|none||markdown文件的预览信息|
|»» images|[string]|true|none||文本中所有的图片的地址|

## POST 构建内容索引

POST /search_pave

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|task_id|query|string| no |任务编号|
|bucket_name|query|string| no |当时请求任务执行的时候指定的bucket|

> Response Examples

> 200 Response

```json
{
  "status": "success",
  "message": "索引构建成功",
  "data": {}
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## GET 内容搜索

GET /content_search

用来检索文档中的关键字的位置

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|task_id|query|string| no |任务编号|
|keyword|query|string| no |想要检索的关键字|

> Response Examples

> 200 Response

```json
{
  "status": "success",
  "message": "搜索成功",
  "data": {
    "result": [
      {
        "page_idx": 0,
        "span_range": [
          15,
          18
        ],
        "bbox": [
          120,
          250,
          380,
          285
        ]
      },
      {
        "page_idx": 2,
        "span_range": [
          8,
          10
        ],
        "bbox": [
          95,
          180,
          420,
          210
        ]
      },
      {
        "page_idx": 5,
        "span_range": [
          22,
          25
        ],
        "bbox": [
          150,
          320,
          450,
          355
        ]
      }
    ]
  }
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» status|string|true|none||none|
|» message|string|true|none||none|
|» data|object|true|none||none|
|»» result|[object]|true|none||none|
|»»» page_idx|integer|true|none||内容对应的页码|
|»»» span_range|[integer]|true|none||在本页中的span的范围（有些肠内容会跨span）|
|»»» bbox|[integer]|true|none||包围检索内容的方框的坐标|

## POST 上传并解析切分office文件

POST /upload-analyze-office-file

> Body Parameters
### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|header_row_number|query|string| no |none|
|key_columns|query|string| no |none|
|body|body|object| yes |none|
|» file|body|string(binary)| no |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

# Data Schema

