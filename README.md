# 重掷 · 最大面追加骰 · 保留最高 K 颗 —— 精确概率服务

一个桌面骰子规则的**精确概率**工具：Svelte 页面编辑规则并绘制总分概率柱图，
Flask 服务用 `fractions.Fraction` 动态规划计算**精确（约分分数）**分布，
Docker Compose 用 `ui` 和 `odds` 两个容器完成真实 HTTP 请求。

> 不使用蒙特卡洛模拟，因此低概率尾部在每次刷新时**完全不变、可复算**。

## 规则

- 输入：原骰数 `n ∈ [1,6]`、每颗面数 `F ∈ [2,8]`、保留颗数 `K ∈ [1,n]`、
  一个重掷面集合（1..F 的任意子集）。
- 每颗骰：
  1. 先掷一次；
  2. 若结果命中重掷集合，则**恰好重掷一次**，新结果为最终面（不再判断重掷）；
  3. 若最终面是最大面 `F`，**再掷一颗附加 dF 并相加**；附加骰不重掷、不再追加。
- 单颗最终点数范围 `1..2F`（其中恰好 `F` 不可能：最终面为 F 时必带 1..F 的附加骰）。
- 对 n 颗的最终点数取**最大的 K 个求和**得到总分。

## 返回内容

`GET /api/distribution?n_dice=&faces=&keep=&threshold=&reroll=&reroll=...`

- `distribution`：从 `K` 到 `2FK` 的**每个**总分（含概率为 0 的不可能值），每项
  - `probability`：**约分分数**字符串（如 `44779/46656`）
  - `decimal`：对应浮点近似，仅用于绘图
- `expected_score`：期望总分（约分分数）
- `probability_at_least`：`P(总分 ≥ threshold)`（约分分数，阈值缺省为 `F+1`，并夹到可行区间）
- `total_probability`：恒为 `"1"`（精确意义下概率之和为 1）

## 目录结构

```
odds/                 Flask + 精确分布引擎
  dice.py             Fraction 引擎：单骰路径、keep-top-K 动态规划、暴力枚举 oracle
  app.py              HTTP 服务（/health、/api/distribution）
  requirements.txt
  Dockerfile          python:3.11-slim + gunicorn，监听 5000
ui/                   Svelte 4 + Vite
  src/App.svelte      规则编辑表单 + 概率柱图（柱上显示原始约分分数）
  e2e/                Playwright 端到端（浏览器核对图表 == 原始分数响应）
  nginx.conf          容器内托管静态资源并把 /api、/health 反代到 odds:5000
  Dockerfile          多阶段构建（node 构建 -> nginx 托管）
tests/                pytest：小面数枚举全部掷骰路径与动态规划对拍
docker-compose.yml    两个服务：odds（仅内网 5000）、ui（映射 8080:80）
```

## 运行（Docker Compose）

```bash
docker compose up --build
# 浏览器打开 http://localhost:8080
# 浏览器 -> ui(nginx:80) -> odds(gunicorn:5000)，均为容器间真实 HTTP
```

## 本地开发

```bash
# odds（需要 flask、gunicorn）
cd odds && python3 app.py            # http://localhost:5000

# ui（另开一个终端，Vite 把 /api 代理到 5000）
cd ui && npm install && npm run dev  # http://localhost:5173
```

## 测试

### 1. 精确对拍（pytest）

以 F=2 的**全部**重掷子集 × 全部 (n,K)、F=3 的全部子集（n≤4）、F=4 的代表子集，
枚举 n 颗骰的**每条随机路径**（首掷/重掷/附加骰三层树的笛卡尔积），按精确联合概率
与动态规划结果逐总分比对 `Fraction` 相等；并覆盖全网格（F=2..8、n=1..6）概率和为 1、
期望、尾部、参数校验及 HTTP 层（含 400 与分数/浮点一致性）。

```bash
python3 -m pytest     # 471 passed
```

### 2. 浏览器主流程（Playwright）

`global-server.js` 启动**真实 Flask(5000)** 与 **Vite preview(4173)**，浏览器只访问
UI 源（经其代理到 odds），核对：

- 每个柱条的 `data-score` 与显示的分数，与该次**原始 JSON 响应**逐条一致；
- 用 BigInt 精确有理数把响应分数相加恰为 `1/1`，与 `total_probability`、期望、尾部一致；
- 修改阈值 / 重掷面 / 面数后，等待**页面自身**发出的响应，页面尾部概率、柱图随之精确更新；
- 经 UI 源直接发起的真实 HTTP 请求（`request.get('/api/...')`）成功且概率和为 1。

```bash
cd ui
npm install
npx playwright install chromium
npm run test:e2e      # 5 passed
```

## 设计要点

- **精确而非模拟**：所有概率为 `fractions.Fraction`，仅在序列化时附带 float 供绘图，
  尾部概率刷新零抖动。
- **两套独立算法互证**：生产用 keep-top-K 状态动态规划（状态为当前 K 大值的升序元组）；
  测试用全路径笛卡尔积暴力枚举作为 oracle。
- **统一入口**：浏览器始终请求同源 `/api`，开发由 Vite 代理、容器由 nginx 代理。
