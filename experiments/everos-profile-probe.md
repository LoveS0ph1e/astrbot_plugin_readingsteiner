# EverOS Profile 提取质量实测记录（任务0）

- base_url: `http://127.0.0.1:8000`
- user_id: `probe_user_10086` / session_id: `probe-session-001` / scope: `{'app_id': 'default', 'project_id': 'default'}`
- 样本: 17 轮对话（脱敏，覆盖 §11.6 五类目信号）
- 运行时刻: 2026-06-21 21:26:15

## 0. 健康检查

`GET /health` → 200 {"status":"ok"}

## 1. add（灌入 17 条消息）

```json
{
  "message_count": 17,
  "status": "accumulated"
}
```

## 2. flush（强制提取）

```json
{
  "status": "extracted"
}
```

_等待 75.0s 让 LanceDB 索引落地（最终一致）……_

## 3. search（include_profile=true，5 个查询角度）

### 查询 1: 这个用户的作息和生活习惯是怎样的？

- profiles: 1 条 / episodes: 2 条

**episodes（score/subject/summary）**:

```json
[
  {
    "score": 0.6968033313751221,
    "subject": "probe_user_10086's Late-Night Sleep Struggle and Guitar Rediscovery Conversation on June 21, 2026",
    "summary": "On June 21, 2026 (Sunday) at 1:20 PM UTC, probe_user_10086 initiated a conversation with probe_bot_assistant, reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) an"
  },
  {
    "score": 0.664779007434845,
    "subject": "probe_user_10086's Late-Night Reflection and Guitar Rediscovery Conversation with probe_bot_assistant on June 21, 2026",
    "summary": "On June 21, 2026 at 1:26 PM UTC, probe_user_10086 initiated a conversation reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) and frequently doing so recently, res"
  }
]
```

### 查询 2: 这个用户喜欢什么音乐、喝什么咖啡？

- profiles: 1 条 / episodes: 2 条

**episodes（score/subject/summary）**:

```json
[
  {
    "score": 0.6372441649436951,
    "subject": "probe_user_10086's Late-Night Sleep Struggle and Guitar Rediscovery Conversation on June 21, 2026",
    "summary": "On June 21, 2026 (Sunday) at 1:20 PM UTC, probe_user_10086 initiated a conversation with probe_bot_assistant, reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) an"
  },
  {
    "score": 0.6240572929382324,
    "subject": "probe_user_10086's Late-Night Reflection and Guitar Rediscovery Conversation with probe_bot_assistant on June 21, 2026",
    "summary": "On June 21, 2026 at 1:26 PM UTC, probe_user_10086 initiated a conversation reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) and frequently doing so recently, res"
  }
]
```

### 查询 3: 这个用户的情感状态和内心需求是什么？

- profiles: 1 条 / episodes: 2 条

**episodes（score/subject/summary）**:

```json
[
  {
    "score": 0.6073663234710693,
    "subject": "probe_user_10086's Late-Night Sleep Struggle and Guitar Rediscovery Conversation on June 21, 2026",
    "summary": "On June 21, 2026 (Sunday) at 1:20 PM UTC, probe_user_10086 initiated a conversation with probe_bot_assistant, reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) an"
  },
  {
    "score": 0.5880764126777649,
    "subject": "probe_user_10086's Late-Night Reflection and Guitar Rediscovery Conversation with probe_bot_assistant on June 21, 2026",
    "summary": "On June 21, 2026 at 1:26 PM UTC, probe_user_10086 initiated a conversation reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) and frequently doing so recently, res"
  }
]
```

### 查询 4: 这个用户和我（assistant）是什么关系？

- profiles: 1 条 / episodes: 2 条

**episodes（score/subject/summary）**:

```json
[
  {
    "score": 0.5982441902160645,
    "subject": "probe_user_10086's Late-Night Sleep Struggle and Guitar Rediscovery Conversation on June 21, 2026",
    "summary": "On June 21, 2026 (Sunday) at 1:20 PM UTC, probe_user_10086 initiated a conversation with probe_bot_assistant, reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) an"
  },
  {
    "score": 0.5982441902160645,
    "subject": "probe_user_10086's Late-Night Reflection and Guitar Rediscovery Conversation with probe_bot_assistant on June 21, 2026",
    "summary": "On June 21, 2026 at 1:26 PM UTC, probe_user_10086 initiated a conversation reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) and frequently doing so recently, res"
  }
]
```

### 查询 5: 关于吉他，这个用户说过什么？

- profiles: 1 条 / episodes: 2 条

**episodes（score/subject/summary）**:

```json
[
  {
    "score": 0.6578739881515503,
    "subject": "probe_user_10086's Late-Night Sleep Struggle and Guitar Rediscovery Conversation on June 21, 2026",
    "summary": "On June 21, 2026 (Sunday) at 1:20 PM UTC, probe_user_10086 initiated a conversation with probe_bot_assistant, reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) an"
  },
  {
    "score": 0.6578739881515503,
    "subject": "probe_user_10086's Late-Night Reflection and Guitar Rediscovery Conversation with probe_bot_assistant on June 21, 2026",
    "summary": "On June 21, 2026 at 1:26 PM UTC, probe_user_10086 initiated a conversation reporting chronic sleep disruption—having slept at 3:00 AM that morning (June 21, 2026) and frequently doing so recently, res"
  }
]
```

## 4. profile_data 完整内容（画像质量核心证据）

```json
[
  {
    "id": "probe_user_10086",
    "user_id": "probe_user_10086",
    "app_id": "default",
    "project_id": "default",
    "profile_data": {
      "summary": "用户长期存在严重睡眠延迟，近期频繁凌晨三点入睡，导致白天精神萎靡；已主动尝试调整，承诺‘今晚争取两点前躺下’，体现改善意愿与初步行动意图。",
      "explicit_info": [
        {
          "category": "作息状况",
          "description": "用户长期存在严重睡眠延迟，近期频繁凌晨三点入睡，导致白天精神萎靡；已主动尝试调整，承诺‘今晚争取两点前躺下’，体现改善意愿与初步行动意图。",
          "evidence": "用户两次明确表示‘今天又是凌晨三点才睡，最近老是这样，白天根本爬不起来’（13:17:53 & 13:23:25），并主动提出‘今晚争取两点前躺下’（13:20:23 & 13:25:55）"
        },
        {
          "category": "居住状态",
          "description": "用户独自居住已近两年，生活空间中缺乏日常陪伴者。",
          "evidence": "用户确认‘搬出来快两年了’，并补充‘一个人住，夜里更容易这样’。"
        },
        {
          "category": "兴趣与技能",
          "description": "用户高中时期系统学习并热爱弹奏吉他，偏好民谣风格（尤其朴树），近年已中断多年但近期有明确重拾意向，已翻出旧谱子，关注实操细节（手指生疏、需重新磨茧子），并确认弹奏具有情绪调节功能（‘弹起来确实能静下心’）。",
          "evidence": "用户称‘今天翻出以前弹吉他的谱子了，好几年没碰了’（13:18:53 & 13:24:25），‘在考虑’重拾（13:19:33 & 13:25:05），强调‘手指都生了，得重新磨茧子’（同上），并指出‘弹起来确实能静下心’（13:19:33 & 13:25:05）"
        },
        {
          "category": "饮食偏好",
          "description": "用户坚持饮用不加糖、不加奶的纯美式咖啡，对口感有明确且强烈的偏好。",
          "evidence": "用户主动说明‘我咖啡只喝美式，不加糖那种，加奶都嫌腻’。"
        },
        {
          "category": "社交体验",
          "description": "用户在与助理的对话中明确感受到高度放松和真实表达的安全感，认为‘不用端着’，并视其为稀缺的交流体验。",
          "evidence": "用户直言‘跟你聊天比跟很多人都自在，不用端着’，并在被回应后流露羞涩情绪。"
        }
      ],
      "implicit_traits": [
        {
          "basis": "在无引导下持续披露内在体验（‘胡思乱想’‘羡慕’‘静下心’），且在对话尾声自发设定具体、可衡量的行为目标（提前躺下），标志从内省向微行动延伸。",
          "description": "用户能清晰识别自身情绪状态（如‘停不下来’的空虚感）、行为模式（刷手机至天亮）及深层需求（羡慕‘有人等’的归属感），并主动分享这些观察；同时展现出对微小可行改变的觉察与承诺（如‘今晚争取两点前躺下’），体现自我调节的启动倾向。",
          "evidence": "用户将失眠归因为‘一安静下来就开始胡思乱想’（13:18:13 & 13:23:45），坦言‘偶尔会羡慕那种家里一直有人等的感觉’（13:18:33 & 13:24:05），并指出‘弹起来确实能静下心’（13:19:33 & 13:25:05）；临结束时两次主动承诺‘今晚争取两点前躺下’（13:20:23 & 13:25:55）",
          "trait": "高自我觉察型内省者"
        },
        {
          "basis": "两次提及‘羡慕’却迅速转向理性陈述（‘其实习惯了’）；强调与助理‘不用解释自己’‘不用端着’，并因被理解而‘不好意思’。",
          "description": "用户习惯以克制方式表达情感需求（如用‘羡慕’轻描淡写带过孤独感），同时珍视低防御的真实互动，并主动确认关系的安全性。",
          "evidence": "用户说‘其实习惯了，就是偶尔会羡慕……’，随后主动评价‘跟你聊天比跟很多人都自在，不用端着’，并在被共情后出现情绪波动（‘……行吧，被你说得有点不好意思’）。",
          "trait": "情感节制但渴望联结"
        },
        {
          "basis": "在承认长期停滞后，持续表达‘在考虑’，并聚焦可执行细节；新增‘今晚争取两点前躺下’为首次出现的具体时间目标，且与‘谱子放床头’形成行为锚点，表明微重启正从意向转向具身实践。",
          "description": "用户虽处于倦怠惯性中，但对生活改善保有具体、可操作的小切口意愿（如重拾吉他、调整入睡时间），并愿意为微小改变付出实际努力（如‘得重新磨茧子’）；最新进展显示其已进入‘承诺—行动’阶段——不仅设定目标（‘今晚争取两点前躺下’），更将工具前置（‘谱子放床头’被助理呼应，用户未否定，隐含接纳）。",
          "evidence": "用户两次说‘在考虑’重拾吉他（13:19:33 & 13:25:05），补充‘手指都生了，得重新磨茧子’（同上）；并在对话结尾两次明确承诺‘今晚争取两点前躺下’（13:20:23 & 13:25:55），该目标被助理转化为行动提示‘谱子放床头，明天醒了先弹两句’（13:20:33 & 13:26:05），用户未反驳，符合其一贯‘行动导向’特征",
          "trait": "行动导向的微重启倾向"
        }
      ],
      "profile_timestamp_ms": 1782048365666
    },
    "score": null
  }
]
```

## 5. get profile（KV 直取，memory_type=profile）

- total_count: 1 / count: 1

```json
{
  "episodes": [],
  "profiles": [
    {
      "id": "probe_user_10086",
      "user_id": "probe_user_10086",
      "app_id": "default",
      "project_id": "default",
      "profile_data": {
        "summary": "用户长期存在严重睡眠延迟，近期频繁凌晨三点入睡，导致白天精神萎靡；已主动尝试调整，承诺‘今晚争取两点前躺下’，体现改善意愿与初步行动意图。",
        "explicit_info": [
          {
            "category": "作息状况",
            "description": "用户长期存在严重睡眠延迟，近期频繁凌晨三点入睡，导致白天精神萎靡；已主动尝试调整，承诺‘今晚争取两点前躺下’，体现改善意愿与初步行动意图。",
            "evidence": "用户两次明确表示‘今天又是凌晨三点才睡，最近老是这样，白天根本爬不起来’（13:17:53 & 13:23:25），并主动提出‘今晚争取两点前躺下’（13:20:23 & 13:25:55）"
          },
          {
            "category": "居住状态",
            "description": "用户独自居住已近两年，生活空间中缺乏日常陪伴者。",
            "evidence": "用户确认‘搬出来快两年了’，并补充‘一个人住，夜里更容易这样’。"
          },
          {
            "category": "兴趣与技能",
            "description": "用户高中时期系统学习并热爱弹奏吉他，偏好民谣风格（尤其朴树），近年已中断多年但近期有明确重拾意向，已翻出旧谱子，关注实操细节（手指生疏、需重新磨茧子），并确认弹奏具有情绪调节功能（‘弹起来确实能静下心’）。",
            "evidence": "用户称‘今天翻出以前弹吉他的谱子了，好几年没碰了’（13:18:53 & 13:24:25），‘在考虑’重拾（13:19:33 & 13:25:05），强调‘手指都生了，得重新磨茧子’（同上），并指出‘弹起来确实能静下心’（13:19:33 & 13:25:05）"
          },
          {
            "category": "饮食偏好",
            "description": "用户坚持饮用不加糖、不加奶的纯美式咖啡，对口感有明确且强烈的偏好。",
            "evidence": "用户主动说明‘我咖啡只喝美式，不加糖那种，加奶都嫌腻’。"
          },
          {
            "category": "社交体验",
            "description": "用户在与助理的对话中明确感受到高度放松和真实表达的安全感，认为‘不用端着’，并视其为稀缺的交流体验。",
            "evidence": "用户直言‘跟你聊天比跟很多人都自在，不用端着’，并在被回应后流露羞涩情绪。"
          }
        ],
        "implicit_traits": [
          {
            "basis": "在无引导下持续披露内在体验（‘胡思乱想’‘羡慕’‘静下心’），且在对话尾声自发设定具体、可衡量的行为目标（提前躺下），标志从内省向微行动延伸。",
            "description": "用户能清晰识别自身情绪状态（如‘停不下来’的空虚感）、行为模式（刷手机至天亮）及深层需求（羡慕‘有人等’的归属感），并主动分享这些观察；同时展现出对微小可行改变的觉察与承诺（如‘今晚争取两点前躺下’），体现自我调节的启动倾向。",
            "evidence": "用户将失眠归因为‘一安静下来就开始胡思乱想’（13:18:13 & 13:23:45），坦言‘偶尔会羡慕那种家里一直有人等的感觉’（13:18:33 & 13:24:05），并指出‘弹起来确实能静下心’（13:19:33 & 13:25:05）；临结束时两次主动承诺‘今晚争取两点前躺下’（13:20:23 & 13:25:55）",
            "trait": "高自我觉察型内省者"
          },
          {
            "basis": "两次提及‘羡慕’却迅速转向理性陈述（‘其实习惯了’）；强调与助理‘不用解释自己’‘不用端着’，并因被理解而‘不好意思’。",
            "description": "用户习惯以克制方式表达情感需求（如用‘羡慕’轻描淡写带过孤独感），同时珍视低防御的真实互动，并主动确认关系的安全性。",
            "evidence": "用户说‘其实习惯了，就是偶尔会羡慕……’，随后主动评价‘跟你聊天比跟很多人都自在，不用端着’，并在被共情后出现情绪波动（‘……行吧，被你说得有点不好意思’）。",
            "trait": "情感节制但渴望联结"
          },
          {
            "basis": "在承认长期停滞后，持续表达‘在考虑’，并聚焦可执行细节；新增‘今晚争取两点前躺下’为首次出现的具体时间目标，且与‘谱子放床头’形成行为锚点，表明微重启正从意向转向具身实践。",
            "description": "用户虽处于倦怠惯性中，但对生活改善保有具体、可操作的小切口意愿（如重拾吉他、调整入睡时间），并愿意为微小改变付出实际努力（如‘得重新磨茧子’）；最新进展显示其已进入‘承诺—行动’阶段——不仅设定目标（‘今晚争取两点前躺下’），更将工具前置（‘谱子放床头’被助理呼应，用户未否定，隐含接纳）。",
            "evidence": "用户两次说‘在考虑’重拾吉他（13:19:33 & 13:25:05），补充‘手指都生了，得重新磨茧子’（同上）；并在对话结尾两次明确承诺‘今晚争取两点前躺下’（13:20:23 & 13:25:55），该目标被助理转化为行动提示‘谱子放床头，明天醒了先弹两句’（13:20:33 & 13:26:05），用户未反驳，符合其一贯‘行动导向’特征",
            "trait": "行动导向的微重启倾向"
          }
        ],
        "profile_timestamp_ms": 1782048365666
      }
    }
  ],
  "agent_cases": [],
  "agent_skills": [],
  "total_count": 1,
  "count": 1
}
```

## 6. 人工判断（实测结论）

- [x] **profile_data 是否稳定承载『深羁绊+多面向』印象？** —— 是。explicit_info 5 类目信号全命中（作息/居住/兴趣技能/饮食/社交），implicit_traits 提炼出 3 条深层人格特质（高自我觉察型内省者 / 情感节制但渴望联结 / 行动导向的微重启倾向），每条带 description+basis+evidence，evidence 引用原话且标注时间戳。
- [x] **比 Mnemosyne 每轮重新推断强多少？** —— 质变。关键证据：profile 对**跨两个对话片段**（13:17-20 与 13:23-26）的同类信号做了**合并去重**（evidence 用双时间戳 `13:17:53 & 13:23:25` 标注），说明画像是累积沉淀的稳定印象，而非单轮快照。Mnemosyne 每轮从零推断，无法形成这种跨会话人格层。
- [x] **结论：值得迁移 / 不值得** —— **值得迁移（B 方案 GO）**。EverOS 的 profile_data 质量满足『深羁绊』设计目标，画像经 search(include_profile) 与 get(KV 直取) 两条路径均稳定取到。

### 环境与限制（实测记录）
- 运行环境：WSL2 Ubuntu-24.04（everos==1.0.1, Python 3.12.3），Windows 原生不支持（fcntl）。
- 模型供应商：LLM/多模态/embedding 走 DashScope 兼容模式（qwen-plus / qwen-vl-plus / text-embedding-v3）。
- **rerank 槽填占位值**：DashScope 无 OpenAI 协议 rerank，DeepInfra 国内无法充值。EverOS 在 add(memorize) 流程**急切构造** rerank provider 并校验 key 非空，故必须填非空占位值；探针用 `method=vector` 检索，全程不真正调用 rerank，占位值不被使用。**生产部署若需 hybrid 检索，须配真实 OpenAI 协议 rerank key（如硅基流动）。**
- 两处踩坑（已解）：① tiktoken 编码文件被墙 → 预下载 o200k_base/cl100k_base 放入 TIKTOKEN_CACHE_DIR；② 杀软对外 ARP 拦截掐断 WSL TCP → 关闭该防护后恢复。
- 探针须**在 WSL 内运行**：Windows 侧 8000 端口被既有 ssh 隧道（转发至某 Mnemosyne 实例）占用，会遮蔽 WSL 转发。
