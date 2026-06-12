# Homepage Design Lock

This document locks the homepage product direction and implementation boundaries for the `ftree` Django family tree application.

The purpose of this file is to prevent design drift while the standalone prototype is converted into backend-driven Django templates, static CSS and static JavaScript.

## 1. Product identity

This is a **family tree app first**.

It is not a generic social media app, not a Facebook clone, and not a memories feed with a tree tab attached.

The correct product identity is:

> A private family tree application where relatives can view generations, connect missing family members, and preserve memories attached to the tree.

Memories, posts, photos and videos are allowed, but they must support the family tree. Every social/media item should attach to at least one of the following:

- person
- couple
- branch
- generation
- family event

If a memory cannot be attached to the tree, it does not belong on the homepage.

## 2. Locked homepage hierarchy

The homepage must follow this order:

1. Sticky header
2. Family tree identity card
3. Search relatives / connect relative action
4. Tree canvas as the dominant main section
5. Generation accordions
6. Relationship rows inside generations
7. Person cards
8. Branch reveal panels
9. Connect missing relatives section
10. Compact memory rails below the tree

The tree must appear before memories.

## 3. Locked visual rules

The homepage must visually communicate family tree within the first screen.

Rules:

- The tree must be visually dominant.
- The first screen must clearly communicate “family tree”.
- Memories must not visually overpower the tree.
- Social/media sections must be compact supporting rails.
- Avoid dashboard clutter.
- Avoid a Facebook-style infinite feed as the homepage.
- Avoid large media cards above the tree canvas.
- Avoid generic social app layout patterns where the tree feels secondary.

The correct visual weighting is:

```text
Tree first.
Memories below.
Everything linked back to relatives.
```

## 4. Locked relationship rules

Generations are the main structure.

Direct family appears first.

Extended relatives are revealed where they belong.

Rules:

- Cousins must not appear in a generic Gen 0 cousins row.
- Cousins belong inside their parent’s reveal panel.
- Aunties and uncles are children of the grandparents generation and open their own branches.
- Siblings can open their own branch panels.
- A person’s spouse and children should appear inside that person’s branch reveal panel.
- Missing relatives should show useful add/connect placeholders.
- Direct-line relatives should be clearly marked.
- Side-branch relatives should be visually distinct from direct-line relatives.

Example:

```text
Gen -2 · Grandparents
  Grandparents couple
    Tawanda + Rudo

  Children of Tawanda & Rudo
    Father          -> direct line
    Uncle John      -> side branch reveal
    Auntie Mary     -> side branch reveal

Tap Uncle John:
  Spouse
    Sarah
  Children
    Cousin Aaron
    Cousin Lisa
```

Cousin Aaron and Cousin Lisa do not appear in a generic Gen 0 cousins row.

## 5. Locked navigation

Use this bottom navigation direction:

```text
Tree | Memory | Connect | People | Menu
```

The active default section is **Tree**.

The `Connect` action should be prominent because the product is not only for viewing relatives, but also for completing missing family branches.

## 6. Locked homepage components

The homepage design is made from these components:

### Header

Sticky app header with product identity.

### Tree identity card

Compact identity panel showing:

- family name
- root person
- key stats
- search relatives input
- connect relative action

### Tree canvas

The dominant homepage section. Contains the generation accordion system.

### Generation accordion

Expandable/collapsible generation block. Examples:

- Gen -2 · Grandparents
- Gen -1 · Parents
- Gen 0 · You & siblings
- Gen +1 · Children
- Gen +2 · Grandchildren

### Relationship row

A row inside a generation. Examples:

- Grandparents couple
- Children of Tawanda & Rudo
- Parents
- You & siblings
- Children

### Person card

Compact relative card showing:

- avatar/photo
- name
- relationship label
- direct/side/spouse/memory badges

### Branch reveal panel

Expandable panel attached to a side-branch person. Shows spouse, children and missing relationship actions.

### Connect missing relatives strip

A compact action section below the tree canvas for:

- add relative
- invite relative
- review pending links
- add memory

### Memory rail

Compact horizontal rail below the tree. Separate rails are allowed for:

- videos
- photo memories
- story posts

Memory rails must not overpower the tree canvas.

### Create/add sheet

Bottom-sheet style create menu for:

- add relative
- add photo memory
- write story
- add video

### Toast feedback

Small user feedback for prototype interactions and future AJAX/HTMX actions.

## 7. Implementation warning

The standalone HTML prototype must **not** be pasted into one giant Django template.

That would create brittle code and make backend integration harder.

The implementation must be split into:

- base template
- homepage template
- partial templates
- static CSS
- static JS
- backend context builder

Do not hardcode demo names directly into final templates except as seeded demo data from the database.

## 8. Suggested Django template/static structure

Use this structure:

```text
templates/
  base.html
  tree/
    home.html
    partials/
      generation_section.html
      relationship_row.html
      person_card.html
      branch_panel.html
      memory_rail.html
      create_sheet.html

static/
  css/
    tree_home.css
  js/
    tree_home.js
```

The `home.html` template should orchestrate the page. It should not contain all component markup inline.

## 9. Suggested backend context shape

The homepage view should prepare backend-driven context similar to this:

```python
context = {
    "family": family,
    "root_person": root_person,
    "stats": {
        "generations": 5,
        "people": 27,
        "memories": 41,
        "missing": 6,
    },
    "generation_sections": [
        {
            "id": "gen-minus-2",
            "label": "Gen -2",
            "title": "Grandparents",
            "subtitle": "Grandparents couple and their children",
            "is_open": True,
            "rows": [
                {
                    "title": "Grandparents couple",
                    "subtitle": "Direct ancestors",
                    "people": grandparents,
                    "add_action_label": "Add branch",
                },
                {
                    "title": "Children of Tawanda & Rudo",
                    "subtitle": "Father continues the direct line. Others reveal their own family.",
                    "people": grandparent_children,
                    "add_action_label": "Add child",
                },
            ],
        },
        {
            "id": "gen-minus-1",
            "label": "Gen -1",
            "title": "Parents",
            "subtitle": "Direct parent generation",
            "is_open": True,
            "rows": [
                {
                    "title": "Parents",
                    "subtitle": "Direct link to root person",
                    "people": parents,
                    "add_action_label": "Add parent",
                },
            ],
        },
        {
            "id": "gen-zero",
            "label": "Gen 0",
            "title": "You & siblings",
            "subtitle": "Root person’s own generation",
            "is_open": True,
            "rows": [
                {
                    "title": "You & siblings",
                    "subtitle": "Same parents, same generation",
                    "people": siblings_and_root,
                    "add_action_label": "Add sibling",
                },
            ],
        },
    ],
    "branch_panels": [
        {
            "owner": uncle_john,
            "id": "branch-uncle-john",
            "title": "Uncle John’s reveal",
            "spouses": uncle_john_spouses,
            "children": uncle_john_children,
            "missing_actions": [],
        },
    ],
    "memory_rails": [
        {
            "title": "Videos",
            "subtitle": "Swipe horizontally",
            "items": video_memories,
        },
        {
            "title": "Photo memories",
            "subtitle": "2 visible",
            "items": photo_memories,
        },
        {
            "title": "Story posts",
            "subtitle": "Written memories",
            "items": story_memories,
        },
    ],
}
```

Person-like objects rendered in person cards should provide or expose:

```python
{
    "id": person.id,
    "name": person.display_name,
    "relationship_label": "Direct parent",
    "avatar_url": person.photo.url if person.photo else None,
    "emoji_fallback": "👤",
    "is_direct_line": True,
    "is_side_branch": False,
    "is_spouse": False,
    "memory_count": 12,
    "branch_panel_id": "branch-uncle-john",
}
```

Memory-like objects rendered in memory rails should provide or expose:

```python
{
    "id": memory.id,
    "title": memory.title,
    "memory_type": memory.memory_type,
    "thumbnail_url": memory.thumbnail.url if memory.thumbnail else None,
    "summary": memory.summary,
    "linked_label": "Auntie Mary’s branch",
    "linked_object_url": memory.get_linked_object_url(),
}
```

## 10. Acceptance criteria

The homepage implementation is only acceptable if:

- [ ] The tree appears before memories.
- [ ] The first screen clearly communicates family tree.
- [ ] The tree canvas is visually dominant.
- [ ] Generation accordions work.
- [ ] Person cards are rendered from backend data.
- [ ] Relationship rows are rendered from backend data.
- [ ] Branch panels reveal related spouse/children.
- [ ] Cousins are inside parent branches.
- [ ] Memory rails are compact.
- [ ] Videos, photos and stories are below the tree.
- [ ] Social content links back to people, couples, branches, generations or events.
- [ ] CSS is not embedded directly in the main homepage template.
- [ ] JavaScript is not embedded directly in the main homepage template.
- [ ] The page works mobile first.
- [ ] The standalone prototype is treated as visual reference only, not as final template code.

## Final locked principle

```text
This app is a family tree first.
The homepage must help users view generations, open branches, connect missing relatives and preserve memories attached to the tree.
```
