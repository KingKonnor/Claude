const RESULTS_URL = "results.json";

let allPosts = [];
let currentFilter = "all";

function formatCount(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
}

function formatRelativeTime(isoString) {
  const then = new Date(isoString).getTime();
  const diffMs = Date.now() - then;
  const diffH = diffMs / (1000 * 60 * 60);
  if (diffH < 1) return `${Math.max(1, Math.round(diffH * 60))}m ago`;
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  return `${Math.round(diffH / 24)}d ago`;
}

function scoreClass(score) {
  if (score >= 70) return "high";
  if (score >= 40) return "mid";
  return "low";
}

function sourceLabel(sourceType, matchedKeyword) {
  if (sourceType === "tracked_account") return "Tracked";
  return matchedKeyword ? `Keyword: ${matchedKeyword}` : "Keyword";
}

function renderPosts() {
  const list = document.getElementById("post-list");
  const template = document.getElementById("post-card-template");

  const posts =
    currentFilter === "all"
      ? allPosts
      : allPosts.filter((p) => p.source_type === currentFilter);

  list.innerHTML = "";

  if (posts.length === 0) {
    const msg = document.createElement("p");
    msg.className = "status-message";
    msg.textContent = "No posts to show yet. Check back after the next scheduled run.";
    list.appendChild(msg);
    return;
  }

  for (const post of posts) {
    const node = template.content.cloneNode(true);

    const badge = node.querySelector(".score-badge");
    badge.textContent = Math.round(post.score.overall);
    badge.classList.add(scoreClass(post.score.overall));

    node.querySelector(".author-name").textContent = post.author.name;
    node.querySelector(".author-username").textContent = `@${post.author.username}`;
    node.querySelector(".followers").textContent = `${formatCount(post.author.followers_count)} followers`;
    node.querySelector(".post-text").textContent = post.text;

    const chips = node.querySelectorAll(".score-chip b");
    chips[0].textContent = post.score.velocity_score.toFixed(0);
    chips[1].textContent = post.score.engagement_ratio_score.toFixed(0);
    chips[2].textContent = post.score.controversy_score.toFixed(0);

    node.querySelector(".post-time").textContent = formatRelativeTime(post.created_at);
    node.querySelector(".source-tag").textContent = sourceLabel(post.source_type, post.matched_keyword);

    const link = node.querySelector(".post-link");
    link.href = post.url;

    list.appendChild(node);
  }
}

function setupFilterBar() {
  const buttons = document.querySelectorAll(".filter-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      currentFilter = btn.dataset.filter;
      renderPosts();
    });
  });
}

async function loadResults() {
  const lastUpdatedEl = document.getElementById("last-updated");
  try {
    const resp = await fetch(`${RESULTS_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    allPosts = (data.posts || []).slice().sort((a, b) => b.score.overall - a.score.overall);

    lastUpdatedEl.textContent = data.last_updated
      ? `Updated ${formatRelativeTime(data.last_updated)}`
      : "No data yet — waiting for the first scheduled run";

    renderPosts();
  } catch (err) {
    lastUpdatedEl.textContent = "Failed to load results";
    document.getElementById("post-list").innerHTML =
      `<p class="status-message">Couldn't load results.json (${err.message}).</p>`;
  }
}

setupFilterBar();
loadResults();
