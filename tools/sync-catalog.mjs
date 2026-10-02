// Generates user-backend/catalog.json from the website's course list
// (user-frontend/src/data/courses.js), so the backend always knows the real
// prices and course details. start-all.bat runs this on every launch.
import { writeFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const { COURSES } = await import(pathToFileURL(join(root, 'user-frontend', 'src', 'data', 'courses.js')).href)

const catalog = COURSES.map(c => ({
  slug: c.slug, title: c.title, domain: c.domain, tagline: c.tagline,
  duration: c.duration, level: c.level, price: c.price, emi: c.emi,
  rating: c.rating, enrolled: c.enrolled, outcomes: c.outcomes,
  instructor: c.instructor, curriculum: c.curriculum.map(m => ({ module: m.w, title: m.t })),
}))
writeFileSync(join(root, 'user-backend', 'catalog.json'), JSON.stringify(catalog, null, 2))
console.log(`catalog.json: ${catalog.length} courses`)
