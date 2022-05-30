module.exports = {
    title: 'MatchesBot',
    description: '赛事信息发布从未如此方便',
    base: '/MatchesBot/',
    themeConfig: {
        smoothScroll: true,
        nav: [
            { text: '主页', link: '/' },
            { text: '指南', link: '/guide/' },
            { text: 'Github', link: 'https://github.com/hank9999/MatchesBot' },
        ],
        sidebar: {
            '/guide/': [{
            title: '指南',
            collapsable: false,
            children: [
                '',
                'cards_and_objects.md',
                'permissions.md',
                'channel_creating.md',
                'unified_sending.md',
                'command_usage.md',
                'FAQ.md'
            ]
            }]
        }
    },
    markdown: {
        extendMarkdown: md => {
            md.use(require("markdown-it-disable-url-encode"));
        }
    }
}