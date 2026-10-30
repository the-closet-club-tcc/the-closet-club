// Build from the project root:
// npx tailwindcss@3.4.17 -c swap/tailwind.config.cjs -i static/css/swap.tailwind.css -o static/css/swap.utilities.css --minify
module.exports = {
    content: ['./templates/swap.html', './templates/swap/**/*.html'],
    prefix: 'sw-',
    important: '.swap-page',
    corePlugins: ['display', 'flexWrap', 'justifyContent', 'gridTemplateColumns', 'gap'],
    theme: {
        screens: { compact: { max: '600px' } },
    },
};
