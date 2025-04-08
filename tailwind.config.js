/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/templates/**/*.html',
    './app/static/**/*.js', // Include JS if you add classes dynamically
  ],
  safelist: [ // Ensure these classes are not purged
    'bg-green-500',
    'bg-lime-500',
    'bg-yellow-500',
    'bg-orange-500',
    'bg-red-500',
    'bg-gray-600', // Also safelist the default/inactive color
  ],
  darkMode: 'class', // Enable dark mode using a class
  theme: {
    extend: {},
  },
  plugins: [],
}

