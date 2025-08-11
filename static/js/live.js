import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from './vendor/CSS2DRenderer.js';

(function() {
  const container = document.getElementById('universe');
  const errBox = document.getElementById('live-error');
  function showError(msg) { if (errBox) { errBox.textContent = msg; errBox.style.display = 'block'; } console.error(msg); }

  const apiUrl = window.UNIVERSE_CFG && window.UNIVERSE_CFG.apiGraph;
  if (!apiUrl) { showError('API-URL fehlt.'); return; }

  // --- Three.js Basics ---
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x000309, 0.00025);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(container.clientWidth, container.clientHeight);
  labelRenderer.domElement.style.position = 'absolute';
  labelRenderer.domElement.style.top = '0';
  labelRenderer.domElement.style.pointerEvents = 'none';
  container.appendChild(labelRenderer.domElement);

  const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 20000);
  camera.position.set(0, 120, 280);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.minDistance = 10;
  controls.maxDistance = 5000;

  // --- Sterne-Hintergrund ---
  function makeStarfield() {
    const starCount = 6000;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
      positions[i * 3 + 0] = (Math.random() - 0.5) * 12000;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 12000;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 12000;
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({ size: 2.2 });
    return new THREE.Points(geometry, material);
  }
  scene.add(makeStarfield());

  // --- Lichter ---
  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
  dirLight.position.set(100, 100, 50);
  scene.add(dirLight);

  // --- State ---
  let graph = { nodes: [], edges: [] };
  let nodesGroup = new THREE.Group();
  let edgesGroup = new THREE.Group();
  scene.add(nodesGroup, edgesGroup);
  const nodeMeshById = new Map();

  function seededRandom(seed) {
    let x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
  }

  function computeLayout(nodes) {
    const groups = {};
    nodes.forEach(n => {
      const g = (n.group || 'Ungruppiert').trim();
      if (!groups[g]) groups[g] = [];
      groups[g].push(n);
    });

    const groupNames = Object.keys(groups);
    const groupRadius = Math.max(120, 60 * Math.sqrt(groupNames.length || 1));
    const centers = {};
    groupNames.forEach((g, idx) => {
      const angle = (idx / groupNames.length) * Math.PI * 2;
      centers[g] = new THREE.Vector3(
        Math.cos(angle || 0) * groupRadius,
        (Math.sin(angle * 2 || 0) * groupRadius) / 4,
        Math.sin(angle || 0) * groupRadius
      );
    });

    const positions = {};
    nodes.forEach(n => {
      const g = (n.group || 'Ungruppiert').trim();
      const center = centers[g] || new THREE.Vector3();
      const spread = 45;
      const rnd1 = seededRandom(n.id + 13);
      const rnd2 = seededRandom(n.id + 71);
      const rnd3 = seededRandom(n.id + 137);
      positions[n.id] = new THREE.Vector3(
        center.x + (rnd1 - 0.5) * spread,
        center.y + (rnd2 - 0.5) * spread,
        center.z + (rnd3 - 0.5) * spread
      );
    });
    return { centers, positions };
  }

  function rebuildScene() {
    for (const child of [...nodesGroup.children]) nodesGroup.remove(child);
    for (const child of [...edgesGroup.children]) edgesGroup.remove(child);
    nodeMeshById.clear();

    const { positions } = computeLayout(graph.nodes);

    // Planeten
    graph.nodes.forEach(n => {
      const pos = positions[n.id];
      const geom = new THREE.SphereGeometry(5.5, 32, 32);
      const mat = new THREE.MeshStandardMaterial({
        color: 0x8bd3ff, roughness: 0.35, metalness: 0.15,
        emissive: 0x001f33, emissiveIntensity: 0.8
      });
      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.copy(pos);
      mesh.userData = { id: n.id, name: n.name, group: n.group, floatPhase: Math.random() * Math.PI * 2 };
      nodesGroup.add(mesh);
      nodeMeshById.set(n.id, mesh);

      // Label
      const div = document.createElement('div');
      div.className = 'label';
      div.textContent = n.name;
      const label = new CSS2DObject(div);
      label.position.set(0, 8, 0);
      mesh.add(label);
    });

    // Kanten
    const lineMat = new THREE.LineBasicMaterial({});
    graph.edges.forEach(e => {
      const a = nodeMeshById.get(e.a);
      const b = nodeMeshById.get(e.b);
      if (!a || !b) return;
      const geometry = new THREE.BufferGeometry().setFromPoints([a.position, b.position]);
      edgesGroup.add(new THREE.Line(geometry, lineMat));
    });
  }

  // Klick → Flug
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  renderer.domElement.addEventListener('click', (event) => {
    const rect = renderer.domElement.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    mouse.set(x, y);
    raycaster.setFromCamera(mouse, camera);
    const hits = raycaster.intersectObjects(nodesGroup.children, false);
    if (hits.length) flyTo(hits[0].object.position);
  });

  function flyTo(targetVec3) {
    const startPos = camera.position.clone();
    const startTarget = controls.target.clone();
    const endTarget = targetVec3.clone();
    const dir = new THREE.Vector3().subVectors(targetVec3, camera.position).normalize();
    const endPos = targetVec3.clone().addScaledVector(dir, 25);
    const duration = 1000; const start = performance.now();
    function animate() {
      const now = performance.now();
      const t = Math.min(1, (now - start) / duration);
      const ease = t < 0.5 ? 2*t*t : -1 + (4 - 2*t)*t;
      camera.position.lerpVectors(startPos, endPos, ease);
      controls.target.lerpVectors(startTarget, endTarget, ease);
      if (t < 1) requestAnimationFrame(animate);
    }
    requestAnimationFrame(animate);
  }

  window.addEventListener('resize', () => {
    const w = container.clientWidth, h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    labelRenderer.setSize(w, h);
  });

  async function fetchGraph() {
    try {
      const res = await fetch(apiUrl, { cache: 'no-store' });
      if (!res.ok) { showError('API-Fehler: ' + res.status + ' ' + res.statusText); return; }
      const data = await res.json();
      graph = data;
      rebuildScene();
      if (graph.nodes.length === 0) showError('Keine Datensätze vorhanden – lege welche an und lade neu.');
      else if (errBox) errBox.style.display = 'none';
    } catch (e) {
      showError('Konnte Graph nicht laden: ' + (e && e.message ? e.message : e));
    }
  }

  fetchGraph();
  setInterval(fetchGraph, 5000);

  function tick(time) {
    nodesGroup.children.forEach(m => {
      const phase = m.userData.floatPhase || 0;
      m.position.y += Math.sin((time * 0.001) + phase) * 0.01;
      m.rotation.y += 0.002;
    });
    controls.update();
    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
