// Tailwind build config (same setup as SecureMy.School). The app serves the built file
// (blf_app/static/css/app.css) itself instead of loading Tailwind from a CDN.
// Rebuild after changing classes in templates:
//   npx tailwindcss@3.4.17 -i blf_app/static/css/tailwind.src.css -o blf_app/static/css/app.css --minify
module.exports = {
    content: ['./blf_app/templates/**/*.html', './blf_app/static/js/**/*.js'],
    theme: {
        extend: {
            colors: {
                forest: { 50: '#f0fdf4', 100: '#dcfce7', 200: '#bbf7d0', 600: '#16a34a', 700: '#15803d', 800: '#166534', 900: '#14532d' },
            },
        },
    },
    plugins: [],
};
