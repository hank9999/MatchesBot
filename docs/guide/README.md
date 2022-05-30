# 介绍
:::tip
简单略读之后可直接前往 [赛事对象和赛事卡片](./cards_and_objects) 开始学习如何使用。
:::

MathcesBot 是一个由 Python 编写的 [开黑啦](https://www.kaiheila.cn) 机器人，其源代码在 Github 已开源，您可以点击导航栏中的 Github 标签查看。

MatchesBot 旨在为各类赛事提供快速生成信息卡片并快速群发的功能，简单易用。

MatchesBot 在与开黑啦交互中采用 [khl.py](https://github.com/TWT233/khl.py) 库，是开黑啦的一个 Python 异步 SDK，支持 WebHook 和 WebSocket 两种回调模式。

MatchesBot 采用 MongoDB 作为数据库存储数据。