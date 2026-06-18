(function () {
  'use strict';

  const TREE_DATA = window.TREE_DATA || { people: [], root_id: null };
  const people = TREE_DATA.people || [];
  const root_id = TREE_DATA.root_id ? String(TREE_DATA.root_id) : null;
  const peopleMap = new Map();
  people.forEach((p) => {
    p.id = String(p.id);
    if (p.father_id) p.father_id = String(p.father_id);
    if (p.mother_id) p.mother_id = String(p.mother_id);
    if (p.partner_id) p.partner_id = String(p.partner_id);
    p.sibling_ids = (p.sibling_ids || []).map(String);
    p.child_ids = (p.child_ids || []).map(String);
    peopleMap.set(p.id, p);
  });

  let expandedNodes = new Set(root_id ? [root_id] : []);
  let scale = 1;
  let panX = 0;
  let panY = 0;
  let initialFitDone = false;
  let focusedId = null;
  let previewHoverId = null;
  let previewHideTimeout = null;
  let longPressTimer = null;
  let longPressStart = null;
  const LONG_PRESS_MS = 500;
  const LONG_PRESS_MOVE_THRESHOLD = 10;
  const minScale = 0.3;
  const maxScale = 2.5;
  const isTouch = window.matchMedia('(pointer: coarse)').matches;

  const wrap = document.getElementById('canvas-wrap');
  const canvas = document.getElementById('canvas');
  const svg = document.getElementById('tree-svg');
  const nodesContainer = document.getElementById('nodes-container');
  const labelsContainer = document.getElementById('labels-container');
  const detailOverlay = document.getElementById('detail-overlay');
  const detailPanel = document.getElementById('detail-panel');

  // Preview layer for hover descendants
  const previewContainer = document.createElement('div');
  previewContainer.className = 'tree-preview-layer';
  if (canvas) canvas.appendChild(previewContainer);

  // -------------------------------------------------------------------------
  // Core algorithm
  // -------------------------------------------------------------------------

  function getVisibleNodes() {
    const visible = new Set();
    if (root_id && peopleMap.has(root_id)) visible.add(root_id);

    expandedNodes.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;
      if (person.father_id) visible.add(person.father_id);
      if (person.mother_id) visible.add(person.mother_id);
      if (person.partner_id) visible.add(person.partner_id);
      person.sibling_ids.forEach((sid) => visible.add(sid));
      person.child_ids.forEach((cid) => visible.add(cid));
    });

    return visible;
  }

  function collectHiddenRelatives(personId, visibleIds) {
    const person = peopleMap.get(personId);
    if (!person) return new Set();
    const hidden = new Set();

    const addIfHidden = (id) => {
      if (id && !visibleIds.has(id)) hidden.add(id);
    };

    // Direct relatives
    [person.father_id, person.mother_id, person.partner_id]
      .filter((id) => id && id !== 'null')
      .forEach(addIfHidden);
    person.sibling_ids.forEach(addIfHidden);
    person.child_ids.forEach(addIfHidden);

    // Siblings' children (nieces/nephews)
    person.sibling_ids.forEach((sid) => {
      const sibling = peopleMap.get(sid);
      if (sibling) sibling.child_ids.forEach(addIfHidden);
    });

    // Parents' siblings (aunts/uncles)
    [person.father_id, person.mother_id].forEach((pid) => {
      const parent = peopleMap.get(pid);
      if (parent) parent.sibling_ids.forEach(addIfHidden);
    });

    // Aunts/uncles' children (cousins)
    [person.father_id, person.mother_id].forEach((pid) => {
      const parent = peopleMap.get(pid);
      if (parent) {
        parent.sibling_ids.forEach((aid) => {
          const auntUncle = peopleMap.get(aid);
          if (auntUncle) auntUncle.child_ids.forEach(addIfHidden);
        });
      }
    });

    return hidden;
  }

  function getHiddenCount(personId, visibleIds) {
    return collectHiddenRelatives(personId, visibleIds).size;
  }

  function getDescendants(personId, maxDepth = 2) {
    const result = new Map();
    const queue = [{ id: personId, depth: 0 }];
    while (queue.length) {
      const { id, depth } = queue.shift();
      if (depth >= maxDepth) continue;
      const person = peopleMap.get(id);
      if (!person) continue;
      person.child_ids.forEach((cid) => {
        if (!result.has(cid)) {
          result.set(cid, depth + 1);
          queue.push({ id: cid, depth: depth + 1 });
        }
      });
    }
    return result;
  }

  function cancelLongPress() {
    if (longPressTimer) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
    }
    longPressStart = null;
  }

  function getHoverNetwork(personId) {
    const network = new Set([personId]);
    const person = peopleMap.get(personId);
    if (!person) return network;

    // All ancestors through both parents (recursive)
    function addAncestors(id) {
      const p = peopleMap.get(id);
      if (!p) return;
      [p.father_id, p.mother_id].forEach((pid) => {
        if (pid && !network.has(pid)) {
          network.add(pid);
          addAncestors(pid);
        }
      });
    }
    addAncestors(personId);

    // Immediate family: partner, children, siblings
    [person.father_id, person.mother_id, person.partner_id]
      .filter((id) => id && id !== 'null')
      .forEach((id) => network.add(id));
    person.child_ids.forEach((cid) => network.add(cid));
    person.sibling_ids.forEach((sid) => network.add(sid));

    return network;
  }

  function clearPreview() {
    if (previewContainer) previewContainer.innerHTML = '';
  }

  function hidePreview() {
    previewHoverId = null;
    if (previewContainer) previewContainer.classList.remove('is-visible');
    if (previewHideTimeout) clearTimeout(previewHideTimeout);
    previewHideTimeout = setTimeout(() => {
      if (!previewHoverId) clearPreview();
    }, 250);
  }

  function showPreview(personId, force = false) {
    if ((!force && isTouch) || !previewContainer) return;
    if (previewHoverId === personId) return;
    previewHoverId = personId;
    if (previewHideTimeout) clearTimeout(previewHideTimeout);

    const visibleIds = getVisibleNodes();
    const descendants = getDescendants(personId, 2);
    const hiddenDescendants = [];
    let deeperCount = 0;
    descendants.forEach((depth, id) => {
      if (!visibleIds.has(id)) {
        hiddenDescendants.push({ id, depth });
      }
    });

    // Count descendants beyond preview depth
    const allDescendants = getDescendants(personId, 50);
    allDescendants.forEach((depth, id) => {
      if (depth > 2 && !visibleIds.has(id)) deeperCount++;
    });

    if (hiddenDescendants.length === 0 && deeperCount === 0) {
      hidePreview();
      return;
    }

    renderPreview(personId, hiddenDescendants, deeperCount);
    previewContainer.classList.add('is-visible');
  }

  function renderPreview(anchorId, descendants, deeperCount) {
    clearPreview();
    const anchor = peopleMap.get(anchorId);
    const anchorNode = nodesContainer.querySelector(`[data-person-id="${anchorId}"]`);
    if (!anchor || !anchorNode) return;

    const anchorRect = {
      left: parseFloat(anchorNode.style.left) + 34,
      top: parseFloat(anchorNode.style.top) + 34,
    };

    const byDepth = {};
    descendants.forEach(({ id, depth }) => {
      if (!byDepth[depth]) byDepth[depth] = [];
      byDepth[depth].push(id);
    });

    const previewSpacing = 120;
    const genGap = 160;
    const fragment = document.createDocumentFragment();

    Object.keys(byDepth)
      .map(Number)
      .sort((a, b) => a - b)
      .forEach((depth) => {
        const ids = byDepth[depth];
        const count = ids.length;
        const totalWidth = (count - 1) * previewSpacing;
        const startX = anchorRect.left - totalWidth / 2;
        const y = anchorRect.top + depth * genGap;

        ids.forEach((id, index) => {
          const person = peopleMap.get(id);
          if (!person) return;
          const x = startX + index * previewSpacing;

          // Find parent for line
          let parentId = null;
          const parent = peopleMap.get(person.father_id) || peopleMap.get(person.mother_id);
          if (parent && (parent.id === anchorId || descendants.find((d) => d.id === parent.id))) {
            parentId = parent.id;
          }

          if (parentId) {
            const parentX = depth === 1 ? anchorRect.left : (
              parseFloat(previewContainer.querySelector(`[data-preview-id="${parentId}"]`)?.style.left || 0) + 34
            );
            const parentY = depth === 1 ? anchorRect.top : (
              parseFloat(previewContainer.querySelector(`[data-preview-id="${parentId}"]`)?.style.top || 0) + 34
            );
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            line.classList.add('tree-preview-line');
            line.style.left = '0';
            line.style.top = '0';
            line.style.width = '100%';
            line.style.height = '100%';
            line.setAttribute('width', '100%');
            line.setAttribute('height', '100%');
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            const midY = (parentY + y) / 2;
            path.setAttribute('d', `M ${parentX} ${parentY} C ${parentX} ${midY}, ${x} ${midY}, ${x} ${y}`);
            path.setAttribute('class', 'tree-preview-path');
            line.appendChild(path);
            fragment.appendChild(line);
          }

          const node = document.createElement('div');
          node.className = 'person-node is-preview';
          node.dataset.previewId = id;
          node.style.left = `${x - 34}px`;
          node.style.top = `${y - 34}px`;

          const avatar = document.createElement('div');
          avatar.className = 'person-avatar';
          avatar.textContent = person.initials;
          node.appendChild(avatar);

          const nameLabel = document.createElement('div');
          nameLabel.className = 'name-label';
          nameLabel.textContent = person.name;
          node.appendChild(nameLabel);

          fragment.appendChild(node);
        });
      });

    if (deeperCount > 0) {
      const badge = document.createElement('div');
      badge.className = 'tree-preview-more';
      badge.textContent = `+${deeperCount} more`;
      badge.style.left = `${anchorRect.left}px`;
      badge.style.top = `${anchorRect.top + 3 * genGap - 20}px`;
      fragment.appendChild(badge);
    }

    previewContainer.appendChild(fragment);
  }

  function focusOnNode(personId) {
    const person = peopleMap.get(personId);
    const node = nodesContainer.querySelector(`[data-person-id="${personId}"]`);
    if (!person || !node || !wrap) return;

    focusedId = personId;
    nodesContainer.querySelectorAll('.person-node.is-focused').forEach((n) => n.classList.remove('is-focused'));
    node.classList.add('is-focused');

    const nodeLeft = parseFloat(node.style.left) + 34;
    const nodeTop = parseFloat(node.style.top) + 34;
    const wrapRect = wrap.getBoundingClientRect();

    // Target: scale 1.1 and centre the node
    const targetScale = Math.min(1.1, maxScale);
    const centerX = wrapRect.width / 2;
    const centerY = wrapRect.height / 2;

    panX = centerX - nodeLeft * targetScale;
    panY = centerY - nodeTop * targetScale;
    scale = targetScale;
    updateTransform();
  }

  function highlightNetwork(personId) {
    const networkIds = getHoverNetwork(personId);
    nodesContainer.querySelectorAll('.person-node').forEach((node) => {
      const id = node.dataset.personId;
      if (networkIds.has(id)) {
        node.classList.add('is-path');
      } else {
        node.classList.add('is-dimmed');
      }
    });
    svg.querySelectorAll('.conn-line').forEach((line) => {
      const from = line.getAttribute('data-from');
      const to = line.getAttribute('data-to');
      if (from && to && networkIds.has(from) && networkIds.has(to)) {
        line.classList.add('is-path');
      } else {
        line.classList.add('is-dimmed');
      }
    });
  }

  function clearNetworkHighlight() {
    nodesContainer.querySelectorAll('.person-node').forEach((node) => {
      node.classList.remove('is-path', 'is-dimmed');
    });
    svg.querySelectorAll('.conn-line').forEach((line) => {
      line.classList.remove('is-path', 'is-dimmed');
    });
  }

  const nodeSpacing = 160;
  const genSpacing = 260;
  const canvasPaddingX = 200;
  const canvasPaddingY = 140;

  function computeCanvasSize(visibleIds) {
    const genGroups = {};
    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;
      if (!genGroups[person.generation]) genGroups[person.generation] = 0;
      genGroups[person.generation]++;
    });

    const maxRowCount = Math.max(1, ...Object.values(genGroups));
    const rowCount = Object.keys(genGroups).length;

    const minWidth = window.innerWidth;
    const minHeight = window.innerHeight - 100;
    // Add extra room for group gaps between sub-groups
    const contentWidth = (maxRowCount + 2) * nodeSpacing + canvasPaddingX * 2;
    const contentHeight = rowCount * genSpacing + canvasPaddingY * 2;

    return {
      width: Math.max(minWidth, contentWidth),
      height: Math.max(minHeight, contentHeight),
      genGroups,
    };
  }

  function calculatePositions(visibleIds, canvasWidth, canvasHeight) {
    const root = peopleMap.get(root_id);
    const positions = {};
    const genGroups = {};
    const genSubGroups = {};

    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;
      const gen = person.generation != null ? person.generation : 0;
      if (!genGroups[gen]) genGroups[gen] = [];
      genGroups[gen].push(id);
    });

    const gens = Object.keys(genGroups)
      .map(Number)
      .sort((a, b) => b - a);
    const centerX = canvasWidth / 2;
    const centerY = canvasHeight / 2;

    // Build direct ancestor/descendant sets from root
    const directAncestors = new Set();
    const ancestorSiblings = new Set();
    const directChildren = new Set();
    const siblingChildren = new Set();

    if (root) {
      [root.father_id, root.mother_id].filter((id) => id && id !== 'null').forEach((pid) => directAncestors.add(pid));
      root.child_ids.forEach((cid) => directChildren.add(cid));
      root.sibling_ids.forEach((sid) => {
        const sibling = peopleMap.get(sid);
        if (sibling) sibling.child_ids.forEach((cid) => siblingChildren.add(cid));
      });

      // Walk up and mark direct ancestors and their siblings
      const walkUp = (person) => {
        if (!person) return;
        [person.father_id, person.mother_id].filter((id) => id && id !== 'null').forEach((pid) => {
          directAncestors.add(pid);
          const parent = peopleMap.get(pid);
          if (parent) {
            parent.sibling_ids.forEach((aid) => ancestorSiblings.add(aid));
            walkUp(parent);
          }
        });
      };
      walkUp(root);
    }

    gens.forEach((gen) => {
      const ids = genGroups[gen];
      const y = centerY - gen * genSpacing;

      const groups = {
        parentSiblings: [],
        parents: [],
        siblings: [],
        partners: [],
        root: [],
        children: [],
        siblingChildren: [],
        other: [],
      };

      ids.forEach((id) => {
        const person = peopleMap.get(id);
        if (!person) return;

        if (id === root_id) {
          groups.root.push(id);
        } else if (gen === 0) {
          if (root && id === root.partner_id) groups.partners.push(id);
          else if (root && root.sibling_ids.includes(id)) groups.siblings.push(id);
          else groups.other.push(id);
        } else if (gen > 0) {
          if (directAncestors.has(id)) groups.parents.push(id);
          else if (ancestorSiblings.has(id)) groups.parentSiblings.push(id);
          else groups.other.push(id);
        } else {
          if (directChildren.has(id)) groups.children.push(id);
          else if (siblingChildren.has(id)) groups.siblingChildren.push(id);
          else groups.other.push(id);
        }
      });

      // Order within row depends on generation
      let rowOrder = [];
      const groupGap = 40;

      if (gen > 0) {
        rowOrder = [
          ...groups.parentSiblings,
          ...groups.parents,
          ...groups.other,
        ];
      } else if (gen === 0) {
        rowOrder = [
          ...groups.siblings,
          ...groups.root,
          ...groups.partners,
          ...groups.other,
        ];
      } else {
        rowOrder = [
          ...groups.siblingChildren,
          ...groups.children,
          ...groups.other,
        ];
      }

      // Build ordered list with group gaps
      const ordered = [];
      let lastGroup = null;
      rowOrder.forEach((id) => {
        let group = 'other';
        if (gen > 0) {
          if (groups.parentSiblings.includes(id)) group = 'parentSiblings';
          else if (groups.parents.includes(id)) group = 'parents';
        } else if (gen === 0) {
          if (groups.siblings.includes(id)) group = 'siblings';
          else if (groups.root.includes(id)) group = 'root';
          else if (groups.partners.includes(id)) group = 'partners';
        } else {
          if (groups.siblingChildren.includes(id)) group = 'siblingChildren';
          else if (groups.children.includes(id)) group = 'children';
        }
        if (lastGroup && lastGroup !== group) {
          ordered.push({ type: 'gap', width: groupGap });
        }
        ordered.push({ type: 'node', id, group });
        lastGroup = group;
      });

      const totalWidth = ordered.reduce((sum, item) => {
        return sum + (item.type === 'gap' ? item.width : nodeSpacing);
      }, 0);
      let currentX = centerX - totalWidth / 2 + nodeSpacing / 2;

      ordered.forEach((item) => {
        if (item.type === 'gap') {
          currentX += item.width;
        } else {
          positions[item.id] = { x: currentX, y };
          currentX += nodeSpacing;
        }
      });

      genSubGroups[gen] = groups;
    });

    return { positions, genGroups, genSubGroups };
  }

  function fitTreeToScreen(canvasWidth, canvasHeight) {
    const header = document.getElementById('tree-header');
    const headerHeight = header ? header.getBoundingClientRect().height : 64;
    const availableHeight = window.innerHeight - headerHeight;
    const availableWidth = window.innerWidth;
    const fitScaleH = (availableHeight - 48) / canvasHeight;
    const fitScaleW = (availableWidth - 48) / canvasWidth;
    const fitScale = Math.min(fitScaleH, fitScaleW);
    if (!initialFitDone) {
      scale = Math.max(minScale, Math.min(1, fitScale));
      initialFitDone = true;
    }
  }

  function setCanvasSize(width, height) {
    if (!canvas || !svg || !nodesContainer || !labelsContainer || !wrap) return;

    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    nodesContainer.style.width = `${width}px`;
    nodesContainer.style.height = `${height}px`;
    labelsContainer.style.width = `${width}px`;
    labelsContainer.style.height = `${height}px`;

    updateTransform();
  }

  function updateTransform() {
    if (!canvas) return;
    canvas.style.transform = `translate(-50%, -50%) translate(${panX}px, ${panY}px) scale(${scale})`;
  }

  function centerCanvas() {
    const header = document.getElementById('tree-header');
    const headerHeight = header ? header.getBoundingClientRect().height : 64;
    if (wrap) wrap.style.top = `${headerHeight}px`;
  }

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------

  function renderTree() {
    if (!wrap || !canvas || !svg || !nodesContainer || !labelsContainer) return;

    const visibleIds = getVisibleNodes();
    const { width, height } = computeCanvasSize(visibleIds);
    const { positions, genGroups, genSubGroups } = calculatePositions(visibleIds, width, height);

    fitTreeToScreen(width, height);
    setCanvasSize(width, height);
    centerCanvas();

    nodesContainer.innerHTML = '';
    labelsContainer.innerHTML = '';
    svg.innerHTML = '';

    const drawn = new Set();
    let lineIndex = 0;

    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      const pos = positions[id];
      if (!person || !pos) return;

      // Partner connection
      if (
        person.partner_id &&
        visibleIds.has(person.partner_id) &&
        id < person.partner_id
      ) {
        const pPos = positions[person.partner_id];
        if (pPos) {
          const key = `${pos.x},${pos.y}-${pPos.x},${pPos.y}`;
          if (!drawn.has(key)) {
            drawn.add(key);
            const path = document.createElementNS(
              'http://www.w3.org/2000/svg',
              'path'
            );
            const midY = (pos.y + pPos.y) / 2;
            path.setAttribute(
              'd',
              `M ${pos.x} ${pos.y} C ${pos.x} ${midY}, ${pPos.x} ${midY}, ${pPos.x} ${pPos.y}`
            );
            path.setAttribute('class', 'conn-line partner');
            path.setAttribute('data-from', id);
            path.setAttribute('data-to', person.partner_id);
            path.style.animationDelay = `${lineIndex++ * 0.08}s`;
            svg.appendChild(path);
          }
        }
      }

      // Parent connections
      [person.father_id, person.mother_id].forEach((pid) => {
        if (pid && visibleIds.has(pid)) {
          const pPos = positions[pid];
          if (pPos) {
            const key = `${pPos.x},${pPos.y}-${pos.x},${pos.y}`;
            if (!drawn.has(key)) {
              drawn.add(key);
              const path = document.createElementNS(
                'http://www.w3.org/2000/svg',
                'path'
              );
              const midY = (pPos.y + pos.y) / 2;
              path.setAttribute(
                'd',
                `M ${pPos.x} ${pPos.y} C ${pPos.x} ${midY}, ${pos.x} ${midY}, ${pos.x} ${pos.y}`
              );
              path.setAttribute('class', 'conn-line parent');
              path.setAttribute('data-from', pid);
              path.setAttribute('data-to', id);
              path.style.animationDelay = `${lineIndex++ * 0.08}s`;
              svg.appendChild(path);
            }
          }
        }
      });

      // Child connections
      person.child_ids.forEach((cid) => {
        if (cid && visibleIds.has(cid)) {
          const cPos = positions[cid];
          if (cPos) {
            const key = `${pos.x},${pos.y}-${cPos.x},${cPos.y}`;
            if (!drawn.has(key)) {
              drawn.add(key);
              const path = document.createElementNS(
                'http://www.w3.org/2000/svg',
                'path'
              );
              const midY = (pos.y + cPos.y) / 2;
              path.setAttribute(
                'd',
                `M ${pos.x} ${pos.y} C ${pos.x} ${midY}, ${cPos.x} ${midY}, ${cPos.x} ${cPos.y}`
              );
              path.setAttribute('class', 'conn-line child');
              path.setAttribute('data-from', id);
              path.setAttribute('data-to', cid);
              path.style.animationDelay = `${lineIndex++ * 0.08}s`;
              svg.appendChild(path);
            }
          }
        }
      });
    });

    // Generation labels based on the groups present in each row
    function labelForRow(gen, groups) {
      if (gen >= 99) return 'Unconnected';
      if (gen === 0) {
        const hasSiblings = groups.siblings.length > 0;
        const hasPartners = groups.partners.length > 0;
        if (hasSiblings && hasPartners) return 'You & Family';
        if (hasSiblings) return 'You & Siblings';
        if (hasPartners) return 'You & Partner';
        return 'You';
      }
      if (gen > 0) {
        const hasParents = groups.parents.length > 0;
        const hasAunts = groups.parentSiblings.length > 0;
        if (hasParents && hasAunts) return gen === 1 ? 'Parents & Aunts/Uncles' : `Gen ${gen} & Aunts/Uncles`;
        if (hasAunts) return gen === 1 ? 'Aunts & Uncles' : `Gen ${gen} Aunts/Uncles`;
        if (hasParents) {
          if (gen === 1) return 'Parents';
          if (gen === 2) return 'Grandparents';
          if (gen === 3) return 'Great-grandparents';
          return `Generation ${gen}`;
        }
        return `Generation ${gen}`;
      }
      // gen < 0
      const hasChildren = groups.children.length > 0;
      const hasSibChildren = groups.siblingChildren.length > 0;
      if (hasChildren && hasSibChildren) return 'Children & Nieces/Nephews';
      if (hasSibChildren) return 'Nieces & Nephews';
      if (gen === -1) return 'Children';
      if (gen === -2) return 'Grandchildren';
      if (gen === -3) return 'Great-grandchildren';
      return `Generation ${Math.abs(gen)}`;
    }

    Object.keys(genGroups)
      .map(Number)
      .sort((a, b) => b - a)
      .forEach((gen) => {
        const ids = genGroups[gen];
        if (!ids || ids.length === 0) return;
        const firstPos = positions[ids[0]];
        const lastPos = positions[ids[ids.length - 1]];
        if (!firstPos || !lastPos) return;
        const midX = (firstPos.x + lastPos.x) / 2;
        const y = firstPos.y - 70;

        const groups = genSubGroups[gen] || {};
        const label = document.createElement('div');
        label.className = 'gen-label';
        label.textContent = labelForRow(gen, groups);
        label.style.left = `${midX}px`;
        label.style.top = `${y}px`;
        labelsContainer.appendChild(label);
      });

    // Person nodes
    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      const pos = positions[id];
      if (!person || !pos) return;

      const hiddenCount = getHiddenCount(id, visibleIds);
      const isExpanded = expandedNodes.has(id);
      const isRoot = id === root_id;

      const node = document.createElement('div');
      node.className = `person-node${isRoot ? ' is-root' : ''}${!person.is_living ? ' is-deceased' : ''}${hiddenCount > 0 ? ' is-expandable' : ''}${focusedId === id ? ' is-focused' : ''}`;
      node.dataset.personId = id;
      node.style.left = `${pos.x - 34}px`;
      node.style.top = `${pos.y - 34}px`;
      node.style.animationDelay = `${Math.random() * 0.15}s`;

      const avatar = document.createElement('div');
      const genClass = isRoot
        ? 'root-avatar'
        : `gen-${String(person.generation).replace('-', 'minus')}`;
      avatar.className = `person-avatar ${genClass}`;
      if (person.avatar_url) {
        const img = document.createElement('img');
        img.src = person.avatar_url;
        img.alt = '';
        img.loading = 'lazy';
        img.onerror = function () {
          this.style.display = 'none';
        };
        avatar.appendChild(img);
      }
      const initials = document.createElement('span');
      initials.className = 'avatar-initials';
      initials.textContent = person.initials;
      avatar.appendChild(initials);
      node.appendChild(avatar);

      // Expand hint ring
      if (hiddenCount > 0) {
        const hint = document.createElement('div');
        hint.className = 'expand-hint';
        node.appendChild(hint);
      }

      // Badge
      if (hiddenCount > 0 || isExpanded) {
        const badge = document.createElement('div');
        badge.className = `person-badge${hiddenCount === 0 ? ' is-zero' : ''}`;
        if (hiddenCount > 0) {
          badge.textContent = hiddenCount;
        } else {
          badge.innerHTML = '<i data-lucide="check"></i>';
        }
        node.appendChild(badge);
      }

      // Name label
      const nameLabel = document.createElement('div');
      nameLabel.className = 'name-label';
      nameLabel.textContent = person.name;
      node.appendChild(nameLabel);

      // Role label
      const groups = genSubGroups[person.generation] || {};
      let roleText = person.role;
      if (id === root_id) {
        roleText = '';
      } else if (groups.siblings && groups.siblings.includes(id)) {
        roleText = 'Sibling';
      } else if (groups.partners && groups.partners.includes(id)) {
        roleText = 'Partner';
      } else if (groups.parentSiblings && groups.parentSiblings.includes(id)) {
        if (person.generation === 1) roleText = 'Aunt/Uncle';
        else if (person.generation === 2) roleText = 'Great-aunt/Great-uncle';
        else roleText = (person.generation - 1) + 'x Great-aunt/Uncle';
      } else if (groups.parents && groups.parents.includes(id)) {
        if (person.generation === 1) roleText = 'Parent';
        else if (person.generation === 2) roleText = 'Grandparent';
        else if (person.generation === 3) roleText = 'Great-grandparent';
        else roleText = (person.generation - 2) + 'x Great-grandparent';
      } else if (groups.children && groups.children.includes(id)) {
        if (person.generation === -1) roleText = 'Child';
        else if (person.generation === -2) roleText = 'Grandchild';
        else if (person.generation === -3) roleText = 'Great-grandchild';
        else roleText = (Math.abs(person.generation) - 2) + 'x Great-grandchild';
      } else if (groups.siblingChildren && groups.siblingChildren.includes(id)) {
        roleText = 'Niece/Nephew';
      } else if (person.generation >= 99) {
        roleText = 'Unconnected';
      }

      const roleLabel = document.createElement('div');
      roleLabel.className = 'role-label';
      roleLabel.textContent = roleText;
      node.appendChild(roleLabel);

      if (person.life_status) {
        const lifeLabel = document.createElement('div');
        lifeLabel.className = 'life-label';
        lifeLabel.textContent = person.life_status;
        node.appendChild(lifeLabel);
      }

      node.addEventListener('mouseenter', () => {
        if (isTouch) return;
        showPreview(id);
        highlightNetwork(id);
      });

      node.addEventListener('mouseleave', () => {
        if (isTouch) return;
        hidePreview();
        clearNetworkHighlight();
      });

      node.addEventListener('click', (e) => {
        e.stopPropagation();
        if (suppressClick) return;
        if (hiddenCount > 0 && !isExpanded) {
          expandedNodes.add(id);
          renderTree();
        } else {
          focusOnNode(id);
          openDetail(id);
        }
      });

      // Long-press on touch devices shows the same preview + highlight as desktop hover
      node.addEventListener('touchstart', (e) => {
        if (e.touches.length !== 1) {
          cancelLongPress();
          return;
        }
        cancelLongPress();
        const t = e.touches[0];
        longPressStart = { x: t.clientX, y: t.clientY, id: t.identifier };
        longPressTimer = setTimeout(() => {
          longPressTimer = null;
          longPressStart = null;
          suppressClick = true;
          showPreview(id, true);
          highlightNetwork(id);
          node.classList.add('is-long-pressed');
        }, LONG_PRESS_MS);
      }, { passive: true });

      node.addEventListener('touchmove', (e) => {
        if (!longPressTimer || !longPressStart) return;
        const t = Array.from(e.touches).find((touch) => touch.identifier === longPressStart.id);
        if (!t) {
          cancelLongPress();
          return;
        }
        const dx = t.clientX - longPressStart.x;
        const dy = t.clientY - longPressStart.y;
        if (Math.hypot(dx, dy) > LONG_PRESS_MOVE_THRESHOLD) {
          cancelLongPress();
        }
      }, { passive: true });

      function endNodeTouch() {
        const wasLongPressed = node.classList.contains('is-long-pressed');
        if (longPressTimer) cancelLongPress();
        if (wasLongPressed) {
          node.classList.remove('is-long-pressed');
          hidePreview();
          clearNetworkHighlight();
          suppressClick = true;
          setTimeout(() => { suppressClick = false; }, 400);
        }
      }
      node.addEventListener('touchend', endNodeTouch, { passive: true });
      node.addEventListener('touchcancel', endNodeTouch, { passive: true });

      nodesContainer.appendChild(node);
    });

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  // -------------------------------------------------------------------------
  // Pan & zoom
  // -------------------------------------------------------------------------

  let isDragging = false;
  let hasDragged = false;
  let dragStart = { x: 0, y: 0 };
  let lastPan = { x: 0, y: 0 };
  let suppressClick = false;

  let pinchStartDistance = 0;
  let pinchStartScale = 1;
  let pinchStartMid = { x: 0, y: 0 };
  let pinchStartPan = { x: 0, y: 0 };

  function clamp(val, lo, hi) {
    return Math.max(lo, Math.min(hi, val));
  }

  function getWrapCentre() {
    const rect = wrap.getBoundingClientRect();
    return { x: rect.width / 2, y: rect.height / 2, rect };
  }

  function zoomBy(factor, screenX, screenY) {
    const { x: cx, y: cy, rect } = getWrapCentre();
    const mouseOffsetX = (screenX === undefined ? cx : screenX - rect.left) - cx;
    const mouseOffsetY = (screenY === undefined ? cy : screenY - rect.top) - cy;
    const newScale = clamp(scale * factor, minScale, maxScale);
    panX += mouseOffsetX * (1 - newScale / scale);
    panY += mouseOffsetY * (1 - newScale / scale);
    scale = newScale;
    updateTransform();
  }

  function fitToScreen() {
    focusedId = null;
    renderTree();
    showToast('Tree fitted to screen');
  }

  function resetView() {
    focusedId = null;
    const visibleIds = getVisibleNodes();
    const { width, height } = computeCanvasSize(visibleIds);
    const header = document.getElementById('tree-header');
    const headerHeight = header ? header.getBoundingClientRect().height : 64;
    const fitScaleH = (window.innerHeight - headerHeight - 48) / height;
    const fitScaleW = (window.innerWidth - 48) / width;
    scale = Math.max(minScale, Math.min(1, Math.min(fitScaleH, fitScaleW)));
    panX = 0;
    panY = 0;
    renderTree();
    showToast('View reset');
  }

  function startDrag(e) {
    if (e.button !== 0) return;
    if (!wrap) return;
    isDragging = true;
    hasDragged = false;
    dragStart.x = e.clientX;
    dragStart.y = e.clientY;
    lastPan.x = panX;
    lastPan.y = panY;
    canvas.classList.add('is-dragging');
  }

  function onDrag(e) {
    if (!isDragging) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged = true;
    panX = lastPan.x + dx;
    panY = lastPan.y + dy;
    updateTransform();
  }

  function endDrag() {
    if (!isDragging) return;
    isDragging = false;
    canvas.classList.remove('is-dragging');
    if (hasDragged) {
      suppressClick = true;
      setTimeout(() => {
        suppressClick = false;
      }, 60);
    }
  }

  function onWheel(e) {
    if (!wrap) return;
    e.preventDefault();
    const factor = Math.exp(-e.deltaY * 0.0015);
    zoomBy(factor, e.clientX, e.clientY);
  }

  function touchDistance(t1, t2) {
    const dx = t1.clientX - t2.clientX;
    const dy = t1.clientY - t2.clientY;
    return Math.hypot(dx, dy);
  }

  function touchMidpoint(t1, t2) {
    return {
      x: (t1.clientX + t2.clientX) / 2,
      y: (t1.clientY + t2.clientY) / 2,
    };
  }

  function startTouch(e) {
    if (!wrap) return;
    if (e.touches.length === 1) {
      const t = e.touches[0];
      isDragging = true;
      hasDragged = false;
      dragStart.x = t.clientX;
      dragStart.y = t.clientY;
      lastPan.x = panX;
      lastPan.y = panY;
      canvas.classList.add('is-dragging');
    } else if (e.touches.length === 2) {
      isDragging = false;
      const [t1, t2] = [e.touches[0], e.touches[1]];
      pinchStartDistance = touchDistance(t1, t2);
      pinchStartScale = scale;
      pinchStartMid = touchMidpoint(t1, t2);
      pinchStartPan.x = panX;
      pinchStartPan.y = panY;
      canvas.classList.add('is-dragging');
    }
  }

  function onTouchMove(e) {
    if (!wrap) return;
    if (e.touches.length === 1 && isDragging) {
      const t = e.touches[0];
      const dx = t.clientX - dragStart.x;
      const dy = t.clientY - dragStart.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        hasDragged = true;
        cancelLongPress();
      }
      panX = lastPan.x + dx;
      panY = lastPan.y + dy;
      updateTransform();
    } else if (e.touches.length === 2) {
      e.preventDefault();
      cancelLongPress();
      const [t1, t2] = [e.touches[0], e.touches[1]];
      const d = touchDistance(t1, t2);
      const mid = touchMidpoint(t1, t2);
      const newScale = clamp(pinchStartScale * (d / pinchStartDistance), minScale, maxScale);
      const { x: cx, y: cy, rect } = getWrapCentre();
      const midOffsetStartX = pinchStartMid.x - rect.left - cx;
      const midOffsetStartY = pinchStartMid.y - rect.top - cy;
      const midOffsetX = mid.x - rect.left - cx;
      const midOffsetY = mid.y - rect.top - cy;
      const scaleRatio = newScale / pinchStartScale;
      panX = pinchStartPan.x * scaleRatio + midOffsetX - midOffsetStartX * scaleRatio;
      panY = pinchStartPan.y * scaleRatio + midOffsetY - midOffsetStartY * scaleRatio;
      scale = newScale;
      updateTransform();
    }
  }

  function endTouch() {
    isDragging = false;
    canvas.classList.remove('is-dragging');
  }

  // -------------------------------------------------------------------------
  // Controls
  // -------------------------------------------------------------------------

  function expandAll() {
    people.forEach((p) => expandedNodes.add(p.id));
    renderTree();
    showToast('All relatives revealed');
  }

  function collapseToRoot() {
    expandedNodes = new Set(root_id ? [root_id] : []);
    renderTree();
    showToast('Collapsed to root only');
  }

  function expandToGen(targetGen) {
    expandedNodes = new Set(root_id ? [root_id] : []);
    people.forEach((p) => {
      if (targetGen >= 0 && p.generation >= 0 && p.generation <= targetGen) {
        expandedNodes.add(p.id);
      } else if (targetGen < 0 && p.generation <= 0 && p.generation >= targetGen) {
        expandedNodes.add(p.id);
      }
    });
    renderTree();
  }

  function showToast(text) {
    const toast = document.getElementById('toast');
    const toastText = document.getElementById('toastText');
    if (!toast || !toastText) return;
    toastText.textContent = text;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2500);
  }

  // -------------------------------------------------------------------------
  // Create sheet
  // -------------------------------------------------------------------------

  let activeCreateTrigger = null;

  function getCreateSheet() {
    return document.getElementById('tree-create-sheet');
  }

  function getCreateSheetBackdrop() {
    return document.getElementById('tree-sheet-backdrop');
  }

  function openCreateSheet(trigger) {
    const createSheet = getCreateSheet();
    const createSheetBackdrop = getCreateSheetBackdrop();
    if (!createSheet || !createSheetBackdrop) return;
    activeCreateTrigger = trigger || activeCreateTrigger;
    createSheet.classList.add('is-open');
    createSheetBackdrop.classList.add('is-open');
    createSheet.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-tree-modal-open');
    const closeBtn = createSheet.querySelector('[data-create-sheet-close]');
    if (closeBtn) setTimeout(() => closeBtn.focus({ preventScroll: true }), 80);
  }

  function closeCreateSheet() {
    const createSheet = getCreateSheet();
    const createSheetBackdrop = getCreateSheetBackdrop();
    if (!createSheet || !createSheetBackdrop) return;
    closeTreeSheetPanels(createSheet);
    createSheet.classList.remove('is-open');
    createSheetBackdrop.classList.remove('is-open');
    createSheet.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('is-tree-modal-open');
    if (activeCreateTrigger) {
      activeCreateTrigger.focus({ preventScroll: true });
      activeCreateTrigger = null;
    }
  }

  function closeTreeSheetPanels(sheet) {
    const createSheet = sheet || getCreateSheet();
    if (!createSheet) return;
    createSheet.querySelectorAll('[data-tree-sheet-panel-content]').forEach((panel) => {
      panel.hidden = true;
    });
    const actions = createSheet.querySelector('.tree-create-actions');
    if (actions) actions.hidden = false;
  }

  function openTreeSheetPanel(panelName) {
    const createSheet = getCreateSheet();
    if (!createSheet) return;
    let activePanel = null;
    createSheet.querySelectorAll('[data-tree-sheet-panel-content]').forEach((panel) => {
      const isActive = panel.dataset.treeSheetPanelContent === panelName;
      panel.hidden = !isActive;
      if (isActive) activePanel = panel;
    });
    if (!activePanel) return;
    const actions = createSheet.querySelector('.tree-create-actions');
    if (actions) actions.hidden = true;
    openCreateSheet();
    const closeBtn = activePanel.querySelector('[data-tree-sheet-panel-close]');
    if (closeBtn) setTimeout(() => closeBtn.focus({ preventScroll: true }), 80);
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return value.replace(/"/g, '\\"');
  }

  function focusPersonInTree(personId) {
    const targetId = String(personId || root_id || '');
    if (!targetId) return;
    const node = document.querySelector(`.person-node[data-person-id="${cssEscape(targetId)}"]`);
    if (!node) return;
    node.classList.add('is-highlighted');
    showToast('Choose a person card to add or invite relatives');
    setTimeout(() => node.classList.remove('is-highlighted'), 1400);
  }

  function openRootDetail() {
    if (!root_id || !peopleMap.has(root_id)) {
      showToast('Choose a person in the tree first');
      return;
    }
    openDetail(root_id);
  }

  function loadTreeSheet(url) {
    if (!url) return;
    closeDetail();
    if (window.htmx && typeof window.htmx.ajax === 'function' && getCreateSheet()) {
      window.htmx.ajax('GET', url, {
        target: '#tree-create-sheet',
        swap: 'outerHTML',
      });
      return;
    }
    window.location.href = url;
  }

  function actionLoadsTreeSheet(action) {
    return [
      'edit',
      'invite',
      'add_parent',
      'add_child',
      'add_partner',
      'add_sibling',
    ].includes(action);
  }

  // -------------------------------------------------------------------------
  // Detail panel
  // -------------------------------------------------------------------------

  function renderRelativeChip(relativeId) {
    const relative = peopleMap.get(relativeId);
    if (!relative) return null;

    const chip = document.createElement('button');
    chip.className = 'detail-relative';
    chip.type = 'button';

    const avatar = document.createElement('span');
    avatar.className = 'detail-relative-avatar';
    if (relative.avatar_url) {
      const img = document.createElement('img');
      img.src = relative.avatar_url;
      img.alt = '';
      img.onerror = function () {
        avatar.textContent = relative.initials;
      };
      avatar.appendChild(img);
    } else {
      avatar.textContent = relative.initials;
    }
    chip.appendChild(avatar);

    const name = document.createElement('span');
    name.textContent = relative.name;
    chip.appendChild(name);

    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      openDetail(relativeId);
    });

    return chip;
  }

  function populateRelatives(containerId, relativeIds) {
    const container = document.getElementById(containerId);
    const section = container ? container.closest('.detail-section') : null;
    if (!container) return;

    container.innerHTML = '';
    const chips = relativeIds
      .map((id) => renderRelativeChip(id))
      .filter(Boolean);

    if (chips.length === 0) {
      if (section) section.style.display = 'none';
      return;
    }

    if (section) section.style.display = '';
    chips.forEach((chip) => container.appendChild(chip));
  }

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function setVisible(el, visible) {
    if (!el) return;
    el.style.display = visible ? '' : 'none';
  }

  function getRelationPicker() {
    return document.getElementById('detail-relation-picker');
  }

  function getRelationToggle() {
    return document.querySelector('[data-detail-menu-toggle]');
  }

  function setDetailRelationPickerOpen(isOpen) {
    const picker = getRelationPicker();
    const toggle = getRelationToggle();
    const wrap = document.getElementById('detail-action-add-relative');
    if (picker) picker.hidden = !isOpen;
    if (toggle) toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    if (wrap) wrap.classList.toggle('is-open', isOpen);
  }

  function closeDetailRelationPicker() {
    setDetailRelationPickerOpen(false);
  }

  function toggleDetailRelationPicker() {
    const picker = getRelationPicker();
    setDetailRelationPickerOpen(!(picker && !picker.hidden));
  }

  function setDetailStatus(person) {
    const statusEl = document.getElementById('detail-status');
    if (!statusEl) return;
    statusEl.innerHTML = '';

    if (person.claimed_by_me) {
      statusEl.textContent = 'Connected to your account';
      statusEl.className = 'detail-status is-claimed';
    } else if (person.is_claimed && person.claimed_by) {
      statusEl.textContent = `Claimed by ${person.claimed_by}`;
      statusEl.className = 'detail-status is-claimed';
    } else {
      statusEl.textContent = 'Not connected to a user account';
      statusEl.className = 'detail-status is-unclaimed';
    }
  }

  function setDetailToolbar(person) {
    const editBtn = document.getElementById('detail-action-edit');
    const inviteBtn = document.getElementById('detail-action-invite');
    const anchorBtn = document.getElementById('detail-action-anchor');
    const descendantsBtn = document.getElementById('detail-action-descendants');
    const storyLink = document.getElementById('detail-action-story');
    const addRelativeWrap = document.getElementById('detail-action-add-relative');
    const deleteBtn = document.getElementById('detail-action-delete');

    setVisible(editBtn, person.can_edit);
    setVisible(inviteBtn, person.can_invite);
    setVisible(anchorBtn, person.can_set_anchor);
    setVisible(descendantsBtn, person.child_ids && person.child_ids.length > 0);
    setVisible(storyLink, true);
    setVisible(addRelativeWrap, person.can_add_relative);
    setVisible(deleteBtn, person.can_delete);
    closeDetailRelationPicker();

    if (editBtn) editBtn.dataset.url = person.urls.edit_name;
    if (inviteBtn) inviteBtn.dataset.url = person.urls.invite;
    if (anchorBtn) anchorBtn.dataset.url = person.urls.set_anchor;
    if (descendantsBtn) descendantsBtn.dataset.url = person.urls.descendants;
    if (storyLink) storyLink.href = person.urls.story_create;
    if (deleteBtn) deleteBtn.dataset.url = person.urls.delete;

    ['parent', 'child', 'partner', 'sibling'].forEach((rel) => {
      const btn = document.querySelector(`[data-detail-action="add_${rel}"]`);
      if (btn && person.urls.add_relative) {
        btn.dataset.url = person.urls.add_relative[rel];
      }
    });
  }

  function setDetailBio(person) {
    const section = document.getElementById('detail-about-section');
    const bioEl = document.getElementById('detail-bio');
    if (!section || !bioEl) return;
    if (person.biography) {
      bioEl.textContent = person.biography;
      setVisible(section, true);
    } else {
      setVisible(section, false);
    }
  }

  function setDetailContent(person) {
    const section = document.getElementById('detail-content-section');
    const statsEl = document.getElementById('detail-content-stats');
    if (!section || !statsEl) return;

    const hasMemories = person.memory_count > 0;
    const hasStories = person.story_count > 0;
    if (!hasMemories && !hasStories) {
      setVisible(section, false);
      return;
    }

    setVisible(section, true);
    statsEl.innerHTML = '';

    if (hasMemories) {
      const memory = document.createElement('a');
      memory.className = 'detail-content-stat';
      memory.href = '/memories/';
      memory.innerHTML = `<strong>${person.memory_count}</strong> <span>Memory${person.memory_count === 1 ? '' : 'ies'}</span>`;
      statsEl.appendChild(memory);
    }

    if (hasStories) {
      const story = document.createElement('a');
      story.className = 'detail-content-stat';
      story.href = '/stories/';
      story.innerHTML = `<strong>${person.story_count}</strong> <span>Story${person.story_count === 1 ? '' : 'ies'}</span>`;
      statsEl.appendChild(story);
    }
  }

  function appendSocialRow(container, label, value) {
    if (!value) return;
    const row = document.createElement('div');
    row.className = 'detail-social-row';
    const labelEl = document.createElement('span');
    labelEl.textContent = label;
    const valueEl = document.createElement('strong');
    valueEl.textContent = value;
    row.appendChild(labelEl);
    row.appendChild(valueEl);
    container.appendChild(row);
  }

  function setDetailSocial(person) {
    const section = document.getElementById('detail-social-section');
    const container = document.getElementById('detail-social');
    if (!section || !container) return;

    const social = person.social || {};
    const recentActivity = social.recent_activity || [];
    const hasSocial =
      social.connected_label ||
      social.pending_invite_label ||
      social.story_count > 0 ||
      social.memory_count > 0 ||
      recentActivity.length > 0;

    if (!hasSocial) {
      setVisible(section, false);
      container.innerHTML = '';
      return;
    }

    setVisible(section, true);
    container.innerHTML = '';
    appendSocialRow(container, 'Connected account', social.connected_label);
    appendSocialRow(container, 'Pending invite', social.pending_invite_label);

    const stats = document.createElement('div');
    stats.className = 'detail-social-stats';
    if (social.story_count > 0) {
      const story = document.createElement('span');
      story.textContent = `${social.story_count} tagged ${social.story_count === 1 ? 'story' : 'stories'}`;
      stats.appendChild(story);
    }
    if (social.memory_count > 0) {
      const memory = document.createElement('span');
      memory.textContent = `${social.memory_count} tagged ${social.memory_count === 1 ? 'memory' : 'memories'}`;
      stats.appendChild(memory);
    }
    if (stats.children.length) container.appendChild(stats);

    if (recentActivity.length) {
      const list = document.createElement('div');
      list.className = 'detail-social-activity';
      recentActivity.forEach((item) => {
        const activity = document.createElement('div');
        const message = document.createElement('strong');
        message.textContent = item.message;
        const date = document.createElement('span');
        date.textContent = item.date;
        activity.appendChild(message);
        activity.appendChild(date);
        list.appendChild(activity);
      });
      container.appendChild(list);
    }
  }

  function openDetail(personId) {
    const person = peopleMap.get(personId);
    if (!person) return;

    const nameEl = document.getElementById('detail-name');
    const roleEl = document.getElementById('detail-role');
    const bornEl = document.getElementById('detail-born');
    const lifeStatusRow = document.getElementById('detail-life-status-row');
    const lifeStatusEl = document.getElementById('detail-life-status');
    const locationEl = document.getElementById('detail-location');
    const genderEl = document.getElementById('detail-gender');
    const avatarEl = document.getElementById('detail-avatar');
    const profileLink = document.getElementById('detail-profile-link');

    if (nameEl) nameEl.textContent = person.name;
    if (roleEl) roleEl.textContent = person.role;
    if (bornEl) bornEl.textContent = person.born || 'Not recorded';
    if (lifeStatusRow && lifeStatusEl) {
      lifeStatusEl.textContent = person.life_status || '';
      lifeStatusRow.style.display = person.life_status ? '' : 'none';
    }
    if (locationEl) locationEl.textContent = person.location || 'Not recorded';
    if (genderEl)
      genderEl.textContent =
        person.gender.charAt(0).toUpperCase() + person.gender.slice(1);

    if (avatarEl) {
      avatarEl.innerHTML = '';
      if (person.avatar_url) {
        const img = document.createElement('img');
        img.src = person.avatar_url;
        img.alt = '';
        img.onerror = function () {
          avatarEl.textContent = person.initials;
        };
        avatarEl.appendChild(img);
      } else {
        avatarEl.textContent = person.initials;
      }
    }

    if (profileLink) {
      profileLink.href = person.urls.drawer;
    }

    setDetailStatus(person);
    setDetailToolbar(person);
    setDetailBio(person);
    setDetailContent(person);
    setDetailSocial(person);

    populateRelatives(
      'detail-parents',
      [person.father_id, person.mother_id].filter((id) => id && id !== 'null')
    );
    populateRelatives(
      'detail-partner',
      person.partner_id ? [person.partner_id] : []
    );
    populateRelatives('detail-siblings', person.sibling_ids);
    populateRelatives('detail-children', person.child_ids);

    detailOverlay.classList.add('is-open');
    detailPanel.classList.add('is-open');

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  function closeDetail() {
    closeDetailRelationPicker();
    detailOverlay.classList.remove('is-open');
    detailPanel.classList.remove('is-open');
  }

  // -------------------------------------------------------------------------
  // Event binding
  // -------------------------------------------------------------------------

  document.addEventListener('click', (e) => {
    const target = e.target;
    if (target.closest('[data-tree-expand-all]')) {
      expandAll();
      return;
    }
    if (target.closest('[data-tree-collapse]')) {
      collapseToRoot();
      return;
    }
    if (target.closest('[data-tree-reset]')) {
      resetView();
      return;
    }
    if (target.closest('[data-zoom-in]')) {
      zoomBy(1.2);
      return;
    }
    if (target.closest('[data-zoom-out]')) {
      zoomBy(0.8);
      return;
    }
    if (target.closest('[data-zoom-fit]')) {
      fitToScreen();
      return;
    }
    if (target.closest('[data-detail-close]')) {
      closeDetail();
      return;
    }
    if (target.closest('.detail-overlay.is-open')) {
      closeDetail();
      return;
    }
    const detailAction = target.closest('[data-detail-action]');
    if (detailAction) {
      const action = detailAction.dataset.detailAction;
      const url = detailAction.dataset.url;
      if (action === 'anchor' && url) {
        fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCsrfToken() } })
          .then((res) => {
            if (res.ok) {
              showToast('Anchor updated');
              window.location.reload();
            } else {
              showToast('Could not update anchor');
            }
          })
          .catch(() => showToast('Could not update anchor'));
      } else if (action === 'delete' && url) {
        if (confirm('Are you sure you want to delete this person? This cannot be undone.')) {
          fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCsrfToken() } })
            .then((res) => {
              if (res.ok) {
                showToast('Person deleted');
                window.location.reload();
              } else {
                showToast('Could not delete person');
              }
            })
            .catch(() => showToast('Could not delete person'));
        }
      } else if (url) {
        if (actionLoadsTreeSheet(action)) {
          closeDetailRelationPicker();
          loadTreeSheet(url);
        } else {
          window.location.href = url;
        }
      }
      return;
    }
    const menuToggle = target.closest('[data-detail-menu-toggle]');
    if (menuToggle) {
      toggleDetailRelationPicker();
      return;
    }
    if (!target.closest('#detail-action-add-relative') && !target.closest('#detail-relation-picker')) {
      closeDetailRelationPicker();
    }
    if (target.closest('[data-create-sheet-trigger]')) {
      openCreateSheet(target.closest('[data-create-sheet-trigger]'));
      return;
    }
    const treeSheetPanel = target.closest('[data-tree-sheet-panel]');
    if (treeSheetPanel) {
      openTreeSheetPanel(treeSheetPanel.dataset.treeSheetPanel);
      return;
    }
    if (target.closest('[data-tree-sheet-panel-close]')) {
      closeTreeSheetPanels();
      return;
    }
    if (target.closest('[data-tree-choose-person]')) {
      closeCreateSheet();
      focusPersonInTree(root_id);
      return;
    }
    if (target.closest('[data-tree-open-root-detail]')) {
      closeCreateSheet();
      openRootDetail();
      return;
    }
    if (target.closest('[data-create-sheet-close]')) {
      closeCreateSheet();
      return;
    }
    if (target.closest('[data-tree-toast]')) {
      const message = target.closest('[data-tree-toast]').dataset.treeToast;
      if (message) showToast(message);
      return;
    }
    const createSheetBackdrop = getCreateSheetBackdrop();
    if (target === createSheetBackdrop && createSheetBackdrop.classList.contains('is-open')) {
      closeCreateSheet();
    }
  });

  if (wrap) {
    wrap.addEventListener('mousedown', startDrag);
    wrap.addEventListener('wheel', onWheel, { passive: false });
    wrap.addEventListener('touchstart', startTouch, { passive: false });
  }
  window.addEventListener('mousemove', onDrag);
  window.addEventListener('mouseup', endDrag);
  window.addEventListener('touchmove', onTouchMove, { passive: false });
  window.addEventListener('touchend', endTouch);
  window.addEventListener('touchcancel', endTouch);

  window.addEventListener('resize', () => {
    centerCanvas();
    renderTree();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      focusedId = null;
      resetView();
    }
  });

  document.body.addEventListener('htmx:afterSwap', (event) => {
    if (
      event.detail &&
      event.detail.target &&
      event.detail.target.id === 'tree-create-sheet'
    ) {
      const createSheet = getCreateSheet();
      const createSheetBackdrop = getCreateSheetBackdrop();
      if (createSheet) {
        createSheet.classList.add('is-open');
        createSheet.setAttribute('aria-hidden', 'false');
      }
      if (createSheetBackdrop) createSheetBackdrop.classList.add('is-open');
      document.body.classList.add('is-tree-modal-open');
      const closeBtn = createSheet ? createSheet.querySelector('[data-create-sheet-close]') : null;
      if (closeBtn) closeBtn.focus({ preventScroll: true });
    }
  });

  // -------------------------------------------------------------------------
  // Init
  // -------------------------------------------------------------------------

  centerCanvas();
  renderTree();
  if (canvas) canvas.classList.add('is-ready');
})();
