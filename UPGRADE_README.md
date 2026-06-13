# HeritageTree — Full UI/UX Upgrade Package

## Files Included

### CSS (Replace `static/css/app.css`)
- `ftree_app.css` — Complete stylesheet with:
  - Generation colour coding (Gold, Blue, Green, Purple)
  - Horizontal scroll cards with snap points
  - Glassmorphism floating bottom nav
  - Bottom sheet design
  - Responsive breakpoints (mobile, tablet, desktop)
  - Lucide icon support
  - All new component styles (cards, badges, avatars, etc.)

### JS (Replace `static/js/app.js`)
- `ftree_app.js` — Updated JavaScript with:
  - Toast system
  - Bottom sheet open/close
  - Drawer management
  - Keyboard-aware bottom nav hiding
  - HTMX integration hooks
  - Lucide icon initialisation
  - Scroll animations (Intersection Observer)

### Templates (Replace in `templates/`)

#### Core Templates
- `base.html` — Updated base template with:
  - Lucide icons via CDN
  - Detail sheet overlay
  - Person detail sheet (bottom sheet pattern)
  - Global sheet container
  - All existing HTMX and Django template tags preserved

- `home.html` — Homepage using all partials

#### Core Partials (`templates/core/`)
- `_header.html` — Sticky glassmorphism header with Lucide icons
- `_bottom_nav.html` — Floating bottom nav with active state logic
- `_left_sidebar.html` — Desktop sidebar with Lucide icons
- `_right_sidebar.html` — Desktop right panel with search, profile, widgets
- `_hero.html` — Hero section with stats and CTA buttons
- `_today_in_history.html` — Today cards with colour-coded icons
- `_tree_placeholder.html` — Fallback tree when no data exists
- `_family_prompt.html` — Family prompt card
- `_memories_carousel.html` — Horizontal scroll memory carousel
- `_recent_activity.html` — Activity feed with Lucide icons
- `_family_champions.html` — Leaderboard with rank badges

#### People App (`templates/people/partials/`)
- `tree_preview.html` — Main tree with horizontal scroll per generation, HTMX drawer loading, generation toggle
- `person_drawer.html` — Person drawer content (HTMX loaded)
- `descendant_generation.html` — Descendant drawer content
- `person_form.html` — Add/edit person form with improved styling

#### Memories App (`templates/memories/`)
- `memory_list.html` — Memory gallery with horizontal scroll cards, empty state

#### Stories App (`templates/stories/`)
- `story_list.html` — Story feed with featured badges, reactions, comments
- `story_form.html` — Create/edit story form with improved styling

#### Social App (`templates/social/`)
- `feed.html` — Activity feed with avatar support

## Installation Instructions

### 1. Backup Existing Files
```bash
cp static/css/app.css static/css/app.css.backup
cp static/js/app.js static/js/app.js.backup
cp -r templates templates.backup
```

### 2. Replace CSS
```bash
cp ftree_app.css static/css/app.css
```

### 3. Replace JS
```bash
cp ftree_app.js static/js/app.js
```

### 4. Replace Templates
```bash
# Base template
cp base.html templates/base.html

# Core partials
cp _header.html templates/core/_header.html
cp _bottom_nav.html templates/core/_bottom_nav.html
cp _left_sidebar.html templates/core/_left_sidebar.html
cp _right_sidebar.html templates/core/_right_sidebar.html
cp _hero.html templates/core/_hero.html
cp _today_in_history.html templates/core/_today_in_history.html
cp _tree_placeholder.html templates/core/_tree_placeholder.html
cp _family_prompt.html templates/core/_family_prompt.html
cp _memories_carousel.html templates/core/_memories_carousel.html
cp _recent_activity.html templates/core/_recent_activity.html
cp _family_champions.html templates/core/_family_champions.html

# Home
cp home.html templates/core/home.html

# People partials
cp tree_preview.html templates/people/partials/tree_preview.html
cp person_drawer.html templates/people/partials/person_drawer.html
cp descendant_generation.html templates/people/partials/descendant_generation.html
cp person_form.html templates/people/partials/person_form.html

# Memories
cp memory_list.html templates/memories/memory_list.html

# Stories
cp story_list.html templates/stories/story_list.html
cp story_form.html templates/stories/story_form.html

# Social
cp feed.html templates/social/feed.html
```

### 5. Add Lucide to Your Project
The base template already includes Lucide via CDN:
```html
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js" defer></script>
```

No additional installation needed.

### 6. Collect Static (if using whitenoise)
```bash
python manage.py collectstatic --noinput
```

### 7. Restart Server
```bash
# Depending on your setup
python manage.py runserver
# or
sudo systemctl restart your-gunicorn-service
```

## Key Design Changes

| Feature | Before | After |
|---------|--------|-------|
| Icons | Emoji (👤🌳🖼️) | Lucide SVG icons |
| Tree layout | Vertical list | Horizontal scroll per generation |
| Generation colours | None | Gold → Blue → Green → Purple |
| Cards | Basic | Premium with shadows, borders, hover states |
| Bottom nav | Fixed bar | Floating glassmorphism pill |
| Person details | Drawer | Bottom sheet (modern mobile pattern) |
| Avatars | Plain text | Gradient backgrounds with initials |
| Empty states | Plain text | Illustrated with icons and CTAs |
| Responsive | Basic | Mobile-first with tablet/desktop enhancements |

## What Was Preserved

All existing Django template logic, HTMX attributes, and backend integration:
- `{% csrf_token %}`
- `hx-get`, `hx-post`, `hx-target`, `hx-swap`
- Django template loops and conditionals
- Model field rendering (`{{ form.first_name }}`)
- URL tags (`{% url 'people:create' %}`)
- Static file tags (`{% static 'css/app.css' %}`)

## Testing Checklist

- [ ] Homepage loads without errors
- [ ] Tree horizontal scroll works on mobile
- [ ] Generation toggle (reveal/hide) still works
- [ ] Person drawer loads via HTMX
- [ ] Bottom sheet opens when tapping person cards
- [ ] Toast notifications appear
- [ ] Bottom nav hides when keyboard opens
- [ ] Desktop sidebar appears on 1040px+ screens
- [ ] All Lucide icons render correctly
- [ ] Form submissions still work
- [ ] Memory/story pages load correctly

## Troubleshooting

**Icons not showing?**
- Check internet connection (Lucide loads from CDN)
- Verify `lucide.createIcons()` is called after DOM ready

**Styles not applying?**
- Run `collectstatic`
- Clear browser cache (Ctrl+Shift+R)
- Check `STATIC_URL` and `STATICFILES_DIRS` settings

**HTMX not working?**
- Verify `htmx.org@2.0.4` loads correctly
- Check `hx-headers` for CSRF token
- Ensure `hx-target` elements exist in DOM
