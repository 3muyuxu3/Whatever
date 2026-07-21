/** @type {import('tailwindcss').Config} */
// Tailwind CSS 配置：将默认无衬线字体设置为 Inter，供全局 font-sans 使用
export default {
    content: ['./index.html', './src/**/*.{js,jsx}'],
    theme: {
        extend: {
            fontFamily: {
                // 所有 Tailwind 的 font-sans 均自动使用 Inter 字体
                sans: ['Inter', 'sans-serif'],
            },
        },
    },
    plugins: [],
}
