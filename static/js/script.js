/* ==========================================================================
   AI Resume Checker - front-end behaviour
   Vanilla JavaScript. No framework, no library, no build step.

   Everything here is progressive enhancement: if any of it fails, the page
   still works because the server already rendered everything.
   ========================================================================== */
(function () {
  "use strict";

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var FINE_POINTER = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* ----------------------------------------------------------------------
     1. Colour theme (light / dark), persisted in localStorage
     ---------------------------------------------------------------------- */
  function initTheme() {
    var toggle = document.getElementById("themeToggle");
    var icon = document.getElementById("themeIcon");
    if (!toggle) return;

    function paint() {
      var dark = document.documentElement.getAttribute("data-theme") === "dark";
      icon.innerHTML = dark ? "&#9789;" : "&#9788;";
      toggle.setAttribute("title", dark ? "Switch to light theme" : "Switch to dark theme");
    }

    paint();
    toggle.addEventListener("click", function () {
      var dark = document.documentElement.getAttribute("data-theme") === "dark";
      var next = dark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("airc-theme", next); } catch (e) { /* storage blocked */ }
      paint();
    });
  }

  /* ----------------------------------------------------------------------
     2. Mobile navigation toggle
     ---------------------------------------------------------------------- */
  function initNav() {
    var toggle = document.getElementById("navToggle");
    var nav = document.getElementById("siteNav");
    if (!toggle || !nav) return;

    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    nav.addEventListener("click", function (event) {
      if (event.target.tagName === "A") {
        nav.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 760) {
        nav.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ----------------------------------------------------------------------
     3. Dismissible flash messages
     ---------------------------------------------------------------------- */
  function initFlash() {
    var area = document.getElementById("flashArea");
    if (!area) return;

    function remove(node) {
      node.style.opacity = "0";
      node.style.transform = "translateY(-6px)";
      node.style.transition = "opacity .2s ease, transform .2s ease";
      window.setTimeout(function () { node.remove(); }, 220);
    }

    area.addEventListener("click", function (event) {
      var button = event.target.closest(".flash-close");
      if (button && button.parentNode) remove(button.parentNode);
    });

    // Errors stay until dismissed; success/info fade on their own.
    window.setTimeout(function () {
      area.querySelectorAll(".flash-success, .flash-warn").forEach(remove);
    }, 8000);
  }

  /* ----------------------------------------------------------------------
     4. Pointer tilt for depth. Writes two angles per element, nothing else.
     ---------------------------------------------------------------------- */
  function initTilt() {
    if (REDUCED || !FINE_POINTER) return;

    var cards = document.querySelectorAll(".tilt");
    var MAX = 6;               // degrees
    var reset = function () {
      cards.forEach(function (card) {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
      });
    };

    cards.forEach(function (card) {
      card.addEventListener("pointermove", function (event) {
        var box = card.getBoundingClientRect();
        var px = (event.clientX - box.left) / box.width;   // 0 -> 1
        var py = (event.clientY - box.top) / box.height;   // 0 -> 1
        card.style.setProperty("--rx", ((0.5 - py) * MAX).toFixed(2) + "deg");
        card.style.setProperty("--ry", ((px - 0.5) * MAX).toFixed(2) + "deg");
      });
      card.addEventListener("pointerleave", function () {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
      });
    });

    window.addEventListener("blur", reset);
  }

  /* ----------------------------------------------------------------------
     5. Count numbers up when they scroll into view
     ---------------------------------------------------------------------- */
  function initCounters() {
    var nodes = document.querySelectorAll("[data-count-to]");
    if (!nodes.length) return;

    function run(node) {
      var target = parseFloat(node.getAttribute("data-count-to")) || 0;
      var decimals = parseInt(node.getAttribute("data-count-decimals") || "0", 10);
      if (REDUCED) { node.textContent = target.toFixed(decimals); return; }

      var duration = 850;
      var start = null;
      function frame(now) {
        if (start === null) start = now;
        var t = Math.min(1, (now - start) / duration);
        var eased = 1 - Math.pow(1 - t, 3);          // easeOutCubic
        node.textContent = (target * eased).toFixed(decimals);
        if (t < 1) window.requestAnimationFrame(frame);
      }
      window.requestAnimationFrame(frame);
    }

    if (!("IntersectionObserver" in window)) {
      nodes.forEach(run);
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          run(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.4 });

    nodes.forEach(function (node) { observer.observe(node); });
  }

  /* ----------------------------------------------------------------------
     6. Fade sections in as they appear
     ---------------------------------------------------------------------- */
  function initReveal() {
    var nodes = document.querySelectorAll(".section");
    if (!nodes.length || REDUCED || !("IntersectionObserver" in window)) return;

    nodes.forEach(function (node) { node.classList.add("reveal"); });

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.04, rootMargin: "0px 0px -40px 0px" });

    nodes.forEach(function (node) { observer.observe(node); });
  }

  /* ----------------------------------------------------------------------
     7. Upload form: drag & drop, validation, progress
     ---------------------------------------------------------------------- */
  function initUploadForm() {
    var form = document.getElementById("uploadForm");
    if (!form) return;

    var dropzone = document.getElementById("dropzone");
    var input = document.getElementById("resumeFile");
    var filename = document.getElementById("dzFilename");
    var filesize = document.getElementById("dzFilesize");
    var hint = document.getElementById("dzHint");
    var errorBox = document.getElementById("fileError");
    var submitBtn = document.getElementById("submitBtn");
    var progress = document.getElementById("progress");
    var progressBar = document.getElementById("progressBar");
    var progressLabel = document.getElementById("progressLabel");

    var MAX_MB = dropzone ? parseInt(dropzone.getAttribute("data-max-mb") || "5", 10) : 5;
    var MAX_BYTES = MAX_MB * 1024 * 1024;

    function humanSize(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / (1024 * 1024)).toFixed(2) + " MB";
    }

    function showError(message) {
      errorBox.textContent = message;
      errorBox.style.display = message ? "block" : "none";
      if (submitBtn) submitBtn.disabled = Boolean(message);
    }

    function describeFile(file) {
      if (!file) return;
      var isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);

      if (!isPdf) {
        showError('"' + file.name + '" is not a PDF. Please choose a PDF file only.');
        return;
      }
      if (file.size > MAX_BYTES) {
        showError("This file is " + humanSize(file.size) +
                  ". The upload limit is " + MAX_MB + " MB.");
        return;
      }
      if (file.size === 0) {
        showError("This file is empty (0 bytes). Please choose a valid PDF.");
        return;
      }

      showError("");
      filename.textContent = file.name;
      filesize.textContent = humanSize(file.size);
      hint.style.display = "none";
      dropzone.classList.add("has-file");
      if (submitBtn) submitBtn.disabled = false;
    }

    if (input) {
      input.addEventListener("change", function () {
        describeFile(input.files && input.files[0]);
      });
    }

    if (dropzone) {
      ["dragenter", "dragover"].forEach(function (name) {
        dropzone.addEventListener(name, function (event) {
          event.preventDefault();
          dropzone.classList.add("dragover");
        });
      });
      ["dragleave", "drop"].forEach(function (name) {
        dropzone.addEventListener(name, function (event) {
          event.preventDefault();
          dropzone.classList.remove("dragover");
        });
      });
      dropzone.addEventListener("drop", function (event) {
        if (!event.dataTransfer || !event.dataTransfer.files.length) return;
        input.files = event.dataTransfer.files;
        describeFile(event.dataTransfer.files[0]);
      });
      // Keyboard support for the drop zone.
      dropzone.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          input.click();
        }
      });
    }

    /* --- Role picker -----------------------------------------------------
       Typing filters the dataset options. If nothing matches, the typed text
       is added as a real option so it is genuinely submitted - the analyzer
       then reports the role as unknown instead of it being silently dropped.
    */
    var roleSelect = document.getElementById("job_role");
    var roleFilter = document.getElementById("roleFilter");
    var roleNotice = document.getElementById("roleFallback");

    if (roleSelect && roleFilter) {
      var CUSTOM_VALUE = "__custom__";
      var customOption = null;
      var options = Array.prototype.slice.call(roleSelect.options);

      roleFilter.addEventListener("input", function () {
        var term = roleFilter.value.trim();
        var needle = term.toLowerCase();
        var hits = 0;

        options.forEach(function (option) {
          if (option.value === "" || option.value === CUSTOM_VALUE) return;
          var hit = !needle || option.text.toLowerCase().indexOf(needle) !== -1;
          option.hidden = !hit;
          option.disabled = !hit;
          if (hit) hits += 1;
        });

        // Remove a previously injected custom option.
        if (customOption) {
          customOption.remove();
          customOption = null;
        }

        if (needle && hits === 0) {
          customOption = document.createElement("option");
          customOption.value = term;
          customOption.textContent = term + " \u2014 custom (not in dataset)";
          customOption.dataset.custom = "1";
          roleSelect.appendChild(customOption);
          roleSelect.value = term;
          if (roleNotice) {
            roleNotice.hidden = false;
            roleNotice.innerHTML = "&ldquo;" + term + "&rdquo; is not in the built-in " +
              "dataset, so no similarity score can be calculated for it. The resume " +
              "quality analysis still runs normally and will report this.";
          }
        } else {
          roleSelect.value = "";
          if (roleNotice) roleNotice.hidden = true;
        }
      });
    }

    /* --- Honest progress indicator ---------------------------------------
       A normal form POST cannot report real upload progress, so this bar only
       shows that the request is in flight. The stage names mirror the actual
       server pipeline; the server still does all the work.
    */
    form.addEventListener("submit", function (event) {
      var file = input.files && input.files[0];
      if (!file) {
        event.preventDefault();
        showError("Please choose a PDF resume first.");
        return;
      }
      if (!/\.pdf$/i.test(file.name)) {
        event.preventDefault();
        showError("Only PDF files are accepted.");
        return;
      }
      if (file.size > MAX_BYTES) {
        event.preventDefault();
        showError("The file is larger than " + MAX_MB + " MB.");
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Analysing\u2026";
      }
      if (!progress) return;

      progress.classList.add("active");
      var stages = [
        [14, "Uploading PDF securely\u2026"],
        [36, "Extracting text (pypdf / pdfplumber)\u2026"],
        [58, "Cleaning text and detecting sections\u2026"],
        [76, "Matching skills and computing TF-IDF\u2026"],
        [90, "Scoring resume, ATS estimate and role match\u2026"],
        [100, "Rendering charts and dashboard\u2026"]
      ];
      var step = 0;
      var timer = window.setInterval(function () {
        step += 1;
        if (step >= stages.length) {
          window.clearInterval(timer);
          return;
        }
        progressBar.style.width = stages[step][0] + "%";
        progressLabel.textContent = stages[step][1];
      }, 430);
    });
  }

  /* ----------------------------------------------------------------------
     8. Results dashboard: print button and floating back-to-top
     ---------------------------------------------------------------------- */
  function initDashboard() {
    var printBtn = document.getElementById("printBtn");
    if (printBtn) printBtn.addEventListener("click", function () { window.print(); });

    var fab = document.getElementById("backToTop");
    if (!fab) return;

    fab.style.display = "none";
    window.addEventListener("scroll", function () {
      fab.style.display = window.scrollY > 560 ? "flex" : "none";
    }, { passive: true });

    fab.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: REDUCED ? "auto" : "smooth" });
    });
  }

  /* ---------------------------------------------------------------------- */
  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initNav();
    initFlash();
    initTilt();
    initCounters();
    initReveal();
    initUploadForm();
    initDashboard();
  });
})();
