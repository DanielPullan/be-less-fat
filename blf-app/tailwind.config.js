// Tailwind build config. The app serves the built file (static/css/app.css) itself, instead of loading Tailwind
// from a CDN. Rebuild after changing classes in templates (yours or Kanto's):
//   npx tailwindcss@3.4.17 -i static/css/tailwind.src.css -o static/css/app.css --minify
module.exports = {
    content: ['./templates/**/*.html', './kanto/templates/**/*.html', './kanto/static/js/**/*.js', './static/js/**/*.js'],
    theme: {
        extend: {
            colors: {
                forest: { 50: '#f0fdf4', 100: '#dcfce7', 200: '#bbf7d0', 300: '#86efac', 600: '#16a34a', 700: '#15803d', 800: '#166534', 900: '#14532d' },
            },
        },
    },
    plugins: [],
};
