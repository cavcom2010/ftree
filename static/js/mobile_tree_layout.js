(function () {
  'use strict';

  const TREE_DATA = window.TREE_DATA || { people: [], root_id: null };
  const people = Array.isArray(TREE_DATA.people) ? TREE_DATA.people : [];
  const rootId = TREE_DATA.root_id ? String(TREE_DATA.root_id) : null;
  const mobileQuery = window.matchMedia('(max-width: 768px)');
  const peopleMap = new Map();

  people.forEach((person) => {
    person.id = String(person.id);
    if (person.father_id) person.father_id = String(person.father_id);
    if (person.mother_id) person.mother_id = String(person.mother_id);
    if (person.partner_id) person.partner_id = String(person.partner_id);
    person.sibling_ids = (person.sibling_ids || []).map(String);
    person.child_ids = (person.child_ids || []).map(String);
    peopleMap.set(person.id, person);
  });

  let mobileMount = null;

  function isMobile() {
    return mobileQuery.matches;
  }

  function getGenerationLabel(gen) {
    if (gen >= 99) return 'Unconnected relatives';
    if (gen === 0) return 'Generation 0 · You, siblings & cousins';
    if (gen > 0) {
      if (gen === 1) return 'Generation 1 · Parents, aunties & uncles';
      if (gen === 2) return 'Generation 2 · Grandparents';
      if (gen === 3) return 'Generation 3 · Great-grandparents';
      return `Generation ${gen} · Ancestors`;
    }
    if (gen === -1) return 'Generation -1 · Children, nieces & nephews';
    if (gen === -2) return 'Generation -2 · Grandchildren';
    if (gen === -3) return 'Generation -3 · Great-grandchildren';
    return `Generation ${gen} · Descendants`;
  }

  function getDisplayRole(person) {
    if (person.id === rootId) return 'You · Gen 0';
    return person.role || `Generation ${person.generation || 0}`;
  }

  function sortPeopleForMobile(list) {
    return [...list].sort((a, b) => {
      if (a.id === rootId) return -1;
      if (b.id === rootId) return 1;
      const aRole = getDisplayRole(a);
      const bRole = getDisplayRole(b);
      const roleCompare = aRole.localeCompare(bRole);
      if (roleCompare !== 0) return roleCompare;
      return (a.name || '').localeCompare(b.name || '');
    });
  }

  function groupPeopleByGeneration() {
    const groups = new Map();
    people.forEach((person) => {
      const gen = Number.isFinite(Number(person.generation)) ? Number(person.generation) : 0;
      if (!groups.has(gen)) groups.set(gen, []);
      groups.get(gen).push(person);
    });
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }

  function makeAvatar(person) {
    const avatar = document.createElement('span');
    avatar.className = 'mobile-person-avatar';

    if (person.avatar_url) {
      const img = document.createElement('img');
      img.src = person.avatar_url;
      img.alt = '';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.onerror = function () {
        img.remove();
        avatar.textContent = person.initials || '?';
      };
      avatar.appendChild(img);
    } else {
      avatar.textContent = person.initials || '?';
    }

    return avatar;
  }

  function makePill(text) {
    const pill = document.createElement('span');
    pill.textContent = text;
    return pill;
  }

  function getRelationshipPills(person) {
    const pills = [];
    const parentCount = [person.father_id, person.mother_id].filter(Boolean).length;
    const childCount = person.child_ids.length;
    const siblingCount = person.sibling_ids.length;

    pills.push(`Gen ${person.generation || 0}`);
    if (person.life_status) pills.push(person.life_status);
    if (parentCount) pills.push(`${parentCount} parent${parentCount === 1 ? '' : 's'}`);
    if (childCount) pills.push(`${childCount} child${childCount === 1 ? '' : 'ren'}`);
    if (siblingCount) pills.push(`${siblingCount} sibling${siblingCount === 1 ? '' : 's'}`);

    return pills.slice(0, 4);
  }

  function createPersonCard(person) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `mobile-person-card${person.id === rootId ? ' is-root' : ''}`;
    card.dataset.personId = person.id;
    card.setAttribute('aria-label', `Open ${person.name || 'person'} profile`);

    card.appendChild(makeAvatar(person));

    const main = document.createElement('span');
    main.className = 'mobile-person-main';

    const name = document.createElement('strong');
    name.textContent = person.name || 'Unnamed person';
    main.appendChild(name);

    const role = document.createElement('small');
    role.textContent = getDisplayRole(person);
    main.appendChild(role);

    const pillWrap = document.createElement('span');
    pillWrap.className = 'mobile-person-pills';
    getRelationshipPills(person).forEach((pillText) => pillWrap.appendChild(makePill(pillText)));
    main.appendChild(pillWrap);

    card.appendChild(main);

    const chevron = document.createElement('span');
    chevron.className = 'mobile-card-chevron';
    chevron.setAttribute('aria-hidden', 'true');
    chevron.textContent = '›';
    card.appendChild(chevron);

    card.addEventListener('click', () => openMobileDetail(person.id));

    return card;
  }

  function createMobileTree() {
    const section = document.createElement('section');
    section.id = 'mobile-tree-vertical';
    section.className = 'mobile-tree-vertical';
    section.setAttribute('aria-label', 'Mobile vertical family tree');

    const intro = document.createElement('div');
    intro.className = 'mobile-tree-intro';
    intro.innerHTML = `
      <p class="mobile-tree-kicker">Mobile tree</p>
      <h2>Vertical family view</h2>
      <p>Ancestors sit above Gen 0 and descendants flow below. Aunties, uncles, siblings and cousins stay inside their own generation instead of stretching sideways.</p>
    `;
    section.appendChild(intro);

    const line = document.createElement('div');
    line.className = 'mobile-tree-line';
    line.setAttribute('aria-hidden', 'true');
    section.appendChild(line);

    const groups = groupPeopleByGeneration();
    if (!groups.length) {
      const empty = document.createElement('div');
      empty.className = 'mobile-tree-empty';
      empty.textContent = 'No people have been added to this tree yet.';
      section.appendChild(empty);
      return section;
    }

    groups.forEach(([generation, generationPeople]) => {
      const generationSection = document.createElement('section');
      generationSection.className = 'mobile-generation';
      generationSection.dataset.generation = String(generation);

      const heading = document.createElement('h3');
      heading.className = 'mobile-generation-heading';
      const headingText = document.createElement('span');
      headingText.textContent = getGenerationLabel(generation);
      heading.appendChild(headingText);
      generationSection.appendChild(heading);

      const stack = document.createElement('div');
      stack.className = 'mobile-person-stack';
      sortPeopleForMobile(generationPeople).forEach((person) => {
        stack.appendChild(createPersonCard(person));
      });
      generationSection.appendChild(stack);

      section.appendChild(generationSection);
    });

    return section;
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '';
  }

  function setVisible(el, visible) {
    if (el) el.style.display = visible ? '' : 'none';
  }

  function renderRelativeChip(relativeId) {
    const relative = peopleMap.get(relativeId);
    if (!relative) return null;

    const chip = document.createElement('button');
    chip.className = 'detail-relative';
    chip.type = 'button';

    const avatar = document.createElement('span');
    avatar.className = 'detail-relative-avatar';
    avatar.textContent = relative.initials || '?';
    chip.appendChild(avatar);

    const name = document.createElement('span');
    name.textContent = relative.name || 'Unnamed person';
    chip.appendChild(name);

    chip.addEventListener('click', () => openMobileDetail(relative.id));
    return chip;
  }

  function populateRelatives(containerId, relativeIds) {
    const container = document.getElementById(containerId);
    const section = container ? container.closest('.detail-section') : null;
    if (!container) return;

    container.innerHTML = '';
    const chips = relativeIds.map(renderRelativeChip).filter(Boolean);
    setVisible(section, chips.length > 0);
    chips.forEach((chip) => container.appendChild(chip));
  }

  function setDetailToolbar(person) {
    const editBtn = document.getElementById('detail-action-edit');
    const inviteBtn = document.getElementById('detail-action-invite');
    const anchorBtn = document.getElementById('detail-action-anchor');
    const descendantsBtn = document.getElementById('detail-action-descendants');
    const storyLink = document.getElementById('detail-action-story');
    const addRelativeWrap = document.getElementById('detail-action-add-relative');
    const deleteBtn = document.getElementById('detail-action-delete');
    const urls = person.urls || {};

    setVisible(editBtn, Boolean(person.can_edit));
    setVisible(inviteBtn, Boolean(person.can_invite));
    setVisible(anchorBtn, Boolean(person.can_set_anchor));
    setVisible(descendantsBtn, person.child_ids && person.child_ids.length > 0);
    setVisible(storyLink, true);
    setVisible(addRelativeWrap, Boolean(person.can_add_relative));
    setVisible(deleteBtn, Boolean(person.can_delete));

    if (editBtn) editBtn.dataset.url = urls.edit_name || '';
    if (inviteBtn) inviteBtn.dataset.url = urls.invite || '';
    if (anchorBtn) anchorBtn.dataset.url = urls.set_anchor || '';
    if (descendantsBtn) descendantsBtn.dataset.url = urls.descendants || '';
    if (storyLink) storyLink.href = urls.story_create || '#';
    if (deleteBtn) deleteBtn.dataset.url = urls.delete || '';

    const addRelativeUrls = urls.add_relative || {};
    ['parent', 'child', 'partner', 'sibling'].forEach((rel) => {
      const btn = document.querySelector(`[data-detail-action="add_${rel}"]`);
      if (btn) btn.dataset.url = addRelativeUrls[rel] || '';
    });

    const picker = document.getElementById('detail-relation-picker');
    const toggle = document.querySelector('[data-detail-menu-toggle]');
    const wrap = document.getElementById('detail-action-add-relative');
    if (picker) picker.hidden = true;
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
    if (wrap) wrap.classList.remove('is-open');
  }

  function openMobileDetail(personId) {
    const person = peopleMap.get(String(personId));
    const overlay = document.getElementById('detail-overlay');
    const panel = document.getElementById('detail-panel');
    if (!person || !overlay || !panel) return;

    setText('detail-name', person.name || 'Unnamed person');
    setText('detail-role', getDisplayRole(person));
    setText('detail-born', person.born || 'Not recorded');
    setText('detail-location', person.location || 'Not recorded');
    setText('detail-gender', person.gender ? person.gender.charAt(0).toUpperCase() + person.gender.slice(1) : 'Not recorded');

    const lifeStatusRow = document.getElementById('detail-life-status-row');
    setText('detail-life-status', person.life_status || '');
    setVisible(lifeStatusRow, Boolean(person.life_status));

    const avatarEl = document.getElementById('detail-avatar');
    if (avatarEl) {
      avatarEl.innerHTML = '';
      if (person.avatar_url) {
        const img = document.createElement('img');
        img.src = person.avatar_url;
        img.alt = '';
        img.onerror = function () {
          avatarEl.textContent = person.initials || '?';
        };
        avatarEl.appendChild(img);
      } else {
        avatarEl.textContent = person.initials || '?';
      }
    }

    const statusEl = document.getElementById('detail-status');
    if (statusEl) {
      statusEl.textContent = person.is_claimed ? 'Connected to a user account' : 'Not connected to a user account';
      statusEl.className = person.is_claimed ? 'detail-status is-claimed' : 'detail-status is-unclaimed';
    }

    const bioSection = document.getElementById('detail-about-section');
    const bioEl = document.getElementById('detail-bio');
    if (bioEl) bioEl.textContent = person.biography || '';
    setVisible(bioSection, Boolean(person.biography));

    const profileLink = document.getElementById('detail-profile-link');
    if (profileLink && person.urls && person.urls.drawer) profileLink.href = person.urls.drawer;

    setDetailToolbar(person);
    populateRelatives('detail-parents', [person.father_id, person.mother_id].filter(Boolean));
    populateRelatives('detail-partner', person.partner_id ? [person.partner_id] : []);
    populateRelatives('detail-siblings', person.sibling_ids || []);
    populateRelatives('detail-children', person.child_ids || []);

    overlay.classList.add('is-open');
    panel.classList.add('is-open');

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  function mountMobileTree() {
    if (!mobileMount) {
      const canvasWrap = document.getElementById('canvas-wrap');
      mobileMount = createMobileTree();
      if (canvasWrap && canvasWrap.parentNode) {
        canvasWrap.parentNode.insertBefore(mobileMount, canvasWrap);
      }
    }

    document.body.classList.toggle('has-mobile-vertical-tree', isMobile());
  }

  function init() {
    if (!people.length) return;
    mountMobileTree();
  }

  init();
  if (typeof mobileQuery.addEventListener === 'function') {
    mobileQuery.addEventListener('change', mountMobileTree);
  } else if (typeof mobileQuery.addListener === 'function') {
    mobileQuery.addListener(mountMobileTree);
  }
})();
