/*
 * Lulebo laundry card
 * Book and cancel laundry times from Home Assistant.
 *   - wide card: the week as a grid (like the Lulebo/Aptus site), arrows switch between this and next week
 *   - narrow card (phones): one day at a time, arrows switch day
 * Served and registered automatically by the Lulebo Tvättstuga integration. No build step, no dependencies.
 *
 *   type: custom:lulebo-laundry-card
 *   entity: sensor.lulebo_laundry_availability   # optional (default)
 *   title: Tvättstuga                              # optional
 *   narrow_width: 560                              # optional, below this width the card shows one day
 */
(() => {
  const VERSION = '1.2.0';

  const SLOT_TIMES = { 0: ['07:00', '10:30'], 1: ['10:30', '14:00'], 2: ['14:00', '17:30'], 3: ['17:30', '21:00'] };

  const TEXT = {
    sv: {
      title: 'Tvättstuga', week: 'Vecka', today: 'Idag', tomorrow: 'Imorgon',
      free: 'Ledig', mine: 'Din tid', taken: 'Upptagen', past: 'Passerad', now: 'Pågår nu',
      book: 'Boka', cancel: 'Avboka', close: 'Avbryt', refresh: 'Uppdatera',
      bookQ: 'Boka tvättid?', cancelQ: 'Avboka tvättid?',
      booked: 'Bokad! Tiden ligger nu i din kalender.', cancelled: 'Avbokad.',
      next: 'Din nästa tid', none: 'Ingen bokad tid', updated: 'Uppdaterad', error: 'Det gick inte',
      prevWeek: 'Förra veckan', nextWeek: 'Nästa vecka', prevDay: 'Föregående dag', nextDay: 'Nästa dag',
      missing: 'Hittar inte', unknownTime: 'okänd tid',
      days: ['Söndag', 'Måndag', 'Tisdag', 'Onsdag', 'Torsdag', 'Fredag', 'Lördag'],
      short: ['Sön', 'Mån', 'Tis', 'Ons', 'Tor', 'Fre', 'Lör'],
      months: ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober', 'november', 'december'],
    },
    en: {
      title: 'Laundry', week: 'Week', today: 'Today', tomorrow: 'Tomorrow',
      free: 'Free', mine: 'Yours', taken: 'Taken', past: 'Passed', now: 'Now',
      book: 'Book', cancel: 'Cancel', close: 'Close', refresh: 'Refresh',
      bookQ: 'Book this time?', cancelQ: 'Cancel this booking?',
      booked: 'Booked! It is in your calendar now.', cancelled: 'Cancelled.',
      next: 'Your next time', none: 'No booking', updated: 'Updated', error: "That didn't work",
      prevWeek: 'Previous week', nextWeek: 'Next week', prevDay: 'Previous day', nextDay: 'Next day',
      missing: 'Entity not found', unknownTime: 'unknown time',
      days: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
      short: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
      months: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    },
  };

  const ICON = {
    plus: '<svg viewBox="0 0 24 24"><path d="M12 6v12M6 12h12"/></svg>',
    minus: '<svg viewBox="0 0 24 24"><path d="M6 12h12"/></svg>',
    left: '<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
    right: '<svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>',
    refresh: '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/></svg>',
    washer: '<svg viewBox="0 0 24 24"><rect x="4" y="2.5" width="16" height="19" rx="3"/><circle cx="12" cy="13" r="4.5"/><path d="M7.5 6h2"/></svg>',
  };

  const pad = (n) => String(n).padStart(2, '0');
  const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parseDate = (s) => { const [y, m, d] = String(s).split('-').map(Number); return new Date(y, m - 1, d); };
  const at = (dateStr, hhmm) => { const d = parseDate(dateStr); const [h, m] = hhmm.split(':').map(Number); d.setHours(h, m, 0, 0); return d; };
  const isoWeek = (d) => {
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    const day = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - day);
    const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    return Math.ceil(((t - y0) / 86400000 + 1) / 7);
  };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  class LuleboLaundryCard extends HTMLElement {
    static getStubConfig() { return { entity: 'sensor.lulebo_laundry_availability' }; }

    setConfig(config) {
      this._config = Object.assign({ entity: 'sensor.lulebo_laundry_availability', narrow_width: 560 }, config || {});
      this._week = null;
      this._day = null;
      this._busy = null;
      this._dialog = null;
      this._toast = null;
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      this._render();
    }

    connectedCallback() {
      if (!this._ro && window.ResizeObserver) {
        this._ro = new ResizeObserver(() => {
          const narrow = this.clientWidth > 0 && this.clientWidth < this._config.narrow_width;
          if (narrow !== this._narrow) { this._narrow = narrow; this._render(); }
        });
      }
      this._ro && this._ro.observe(this);
      // keep "past" slots and today's highlight correct without waiting for a state change
      this._tick = setInterval(() => this._render(), 60000);
    }

    disconnectedCallback() {
      this._ro && this._ro.disconnect();
      clearInterval(this._tick);
    }

    set hass(hass) {
      const old = this._hass;
      this._hass = hass;
      const s = hass.states[this._config.entity];
      const so = old && old.states[this._config.entity];
      if (!old || s !== so || (old.language !== hass.language)) this._render();
    }

    getCardSize() { return this._narrow ? 6 : 7; }
    getGridOptions() { return { columns: 'full', rows: 'auto', min_columns: 6 }; }

    // ------------------------------------------------------------------ data
    get _t() { return TEXT[(this._hass && String(this._hass.language || '').startsWith('sv')) ? 'sv' : 'en']; }

    _data() {
      const st = this._hass && this._hass.states[this._config.entity];
      if (!st) return null;
      const a = st.attributes || {};
      const today = new Date(); today.setHours(0, 0, 0, 0);
      let days = Array.isArray(a.days) && a.days.length ? a.days.slice() : null;
      if (!days) {
        const mon = new Date(today); mon.setDate(mon.getDate() - ((mon.getDay() + 6) % 7));
        days = Array.from({ length: 14 }, (_, i) => { const d = new Date(mon); d.setDate(d.getDate() + i); return isoDate(d); });
      }
      const times = {};
      const src = a.slot_times || SLOT_TIMES;
      Object.keys(src).forEach((k) => { times[String(k)] = src[k]; });
      const free = {};
      Object.entries(a.raw_slots || {}).forEach(([d, slots]) => { free[d] = (slots || []).map(String); });
      const mine = {};
      if (a.my_bookings) Object.entries(a.my_bookings).forEach(([d, s]) => { mine[d] = s === null || s === undefined ? null : String(s); });
      else Object.keys(a.current_bookings || {}).forEach((d) => { mine[d] = null; });
      return { days, times, free, mine, updated: a.updated || st.last_updated };
    }

    _status(data, date, slot) {
      const [start, end] = data.times[slot];
      const now = new Date();
      const isMine = date in data.mine && (data.mine[date] === slot || data.mine[date] === null);
      if (isMine) return now >= at(date, start) && now < at(date, end) ? 'now' : (now >= at(date, end) ? 'past' : 'mine');
      if (now >= at(date, end)) return 'past';
      return (data.free[date] || []).includes(slot) ? 'free' : 'taken';
    }

    _dayLabel(dateStr, long = true) {
      const t = this._t; const d = parseDate(dateStr);
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const diff = Math.round((d - today) / 86400000);
      const name = diff === 0 ? t.today : diff === 1 ? t.tomorrow : t.days[d.getDay()];
      return long ? `${name} ${d.getDate()} ${t.months[d.getMonth()]}` : name;
    }

    _nextBooking(data) {
      const now = new Date();
      const list = Object.entries(data.mine)
        .map(([date, slot]) => ({ date, slot, end: slot !== null && data.times[slot] ? at(date, data.times[slot][1]) : at(date, '23:59') }))
        .filter((b) => b.end > now)
        .sort((x, y) => x.end - y.end);
      return list[0] || null;
    }

    // --------------------------------------------------------------- actions
    async _call(kind, date, slot) {
      const t = this._t;
      this._dialog = null;
      this._busy = `${date}|${slot}`;
      this._render();
      try {
        if (kind === 'book') await this._hass.callService('lulebo_laundry', 'book', { date, slot: String(slot) });
        else await this._hass.callService('lulebo_laundry', 'cancel', { date });
        this._showToast(kind === 'book' ? t.booked : t.cancelled, false);
      } catch (err) {
        this._showToast(`${t.error}: ${(err && err.message) || err}`, true);
      }
      this._busy = null;
      this._render();
    }

    async _refresh() {
      this._busy = 'refresh';
      this._render();
      try {
        if (this._hass.services && this._hass.services.lulebo_laundry && this._hass.services.lulebo_laundry.refresh) {
          await this._hass.callService('lulebo_laundry', 'refresh', {});
        } else {
          await this._hass.callService('homeassistant', 'update_entity', { entity_id: this._config.entity });
        }
      } catch (err) {
        this._showToast(`${this._t.error}: ${(err && err.message) || err}`, true);
      }
      this._busy = null;
      this._render();
    }

    _showToast(text, error) {
      this._toast = { text, error };
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => { this._toast = null; this._render(); }, error ? 6000 : 3500);
    }

    // ---------------------------------------------------------------- render
    _tile(data, date, slot, narrow) {
      const t = this._t;
      const st = this._status(data, date, slot);
      const [start, end] = data.times[slot];
      const busy = this._busy === `${date}|${slot}`;
      const actionable = st === 'free' || st === 'mine';
      const label = { free: t.free, mine: t.mine, now: t.now, taken: t.taken, past: t.past }[st];
      const btn = busy ? '<span class="spin"></span>'
        : st === 'free' ? `<span class="act">${narrow ? `<span class="pill">${t.book}</span>` : ICON.plus}</span>`
        : st === 'mine' ? `<span class="act">${narrow ? `<span class="pill ghost">${t.cancel}</span>` : ICON.minus}</span>` : '';
      const attrs = actionable && !busy ? ` role="button" tabindex="0" data-kind="${st === 'free' ? 'book' : 'cancel'}" data-date="${date}" data-slot="${slot}"` : '';
      const aria = `${this._dayLabel(date)} ${start}–${end}: ${label}`;
      return narrow
        ? `<div class="tile row ${st}${busy ? ' busy' : ''}"${attrs} aria-label="${esc(aria)}">
             <div class="tt"><span class="time">${start}<span class="dash">–</span>${end}</span><span class="lbl">${label}</span></div>${btn}</div>`
        : `<div class="tile ${st}${busy ? ' busy' : ''}"${attrs} aria-label="${esc(aria)}">
             <span class="time">${start}<span class="end">${end}</span></span><span class="lbl">${label}</span>${btn}</div>`;
    }

    _render() {
      if (!this.shadowRoot || !this._config) return;
      const t = this._t;
      const data = this._hass ? this._data() : null;
      const narrow = this._narrow !== undefined ? this._narrow : (this.clientWidth > 0 && this.clientWidth < this._config.narrow_width);
      const title = this._config.title || t.title;
      let body = '';
      let nav = '';

      if (!this._hass) body = '';
      else if (!data) body = `<div class="empty">${t.missing}: ${esc(this._config.entity)}</div>`;
      else {
        const slots = Object.keys(data.times);
        const todayIso = isoDate(new Date());
        if (narrow) {
          // one day at a time, starting today; past days are skipped
          const first = Math.max(0, data.days.indexOf(todayIso));
          if (this._day === null || this._day < first) this._day = first;
          if (this._day > data.days.length - 1) this._day = data.days.length - 1;
          const date = data.days[this._day];
          nav = `<div class="daynav">
              <button class="nav" data-nav="-1" ${this._day <= first ? 'disabled' : ''} aria-label="${t.prevDay}">${ICON.left}</button>
              <div class="dayname"><b>${esc(this._dayLabel(date, false))}</b><span>${parseDate(date).getDate()} ${t.months[parseDate(date).getMonth()]}</span></div>
              <button class="nav" data-nav="1" ${this._day >= data.days.length - 1 ? 'disabled' : ''} aria-label="${t.nextDay}">${ICON.right}</button>
            </div>`;
          body = `<div class="list">${slots.map((s) => this._tile(data, date, s, true)).join('')}</div>`;
        } else {
          const weeks = Math.max(1, Math.ceil(data.days.length / 7));
          if (this._week === null) {
            // open on the week with the next bookable time (e.g. next week on a Sunday evening)
            const now = new Date();
            const lastSlot = Object.values(data.times).reduce((m, t) => (t[1] > m ? t[1] : m), '00:00');
            const idx = data.days.findIndex((d) => at(d, lastSlot) > now);
            this._week = idx < 0 ? 0 : Math.floor(idx / 7);
          }
          if (this._week > weeks - 1) this._week = weeks - 1;
          const week = data.days.slice(this._week * 7, this._week * 7 + 7);
          nav = `<div class="weeknav">
              <button class="nav" data-week="-1" ${this._week <= 0 ? 'disabled' : ''} aria-label="${t.prevWeek}">${ICON.left}</button>
              <span>${t.week} ${isoWeek(parseDate(week[0]))}</span>
              <button class="nav" data-week="1" ${this._week >= weeks - 1 ? 'disabled' : ''} aria-label="${t.nextWeek}">${ICON.right}</button>
            </div>`;
          const head = week.map((d) => {
            const dd = parseDate(d);
            return `<div class="dh${d === todayIso ? ' today' : ''}"><span>${t.short[dd.getDay()]}</span><b>${dd.getDate()}</b></div>`;
          }).join('');
          const cells = slots.map((s) => week.map((d) => this._tile(data, d, s, false)).join('')).join('');
          body = `<div class="grid" style="--cols:${week.length}">${head}${cells}</div>`;
        }
        const nb = this._nextBooking(data);
        const nbDay = nb ? (narrow ? (() => { const d = parseDate(nb.date); return `${this._dayLabel(nb.date, false).slice(0, 3)} ${d.getDate()}/${d.getMonth() + 1}`; })() : this._dayLabel(nb.date)) : '';
        const nextTxt = nb
          ? `${esc(nbDay)} · ${nb.slot !== null && data.times[nb.slot] ? data.times[nb.slot].join('–') : t.unknownTime}`
          : t.none;
        body = `<div class="next${nb ? ' has' : ''}"><span class="dot"></span><span>${nb ? t.next + ': ' : ''}<b>${nextTxt}</b></span></div>` + body;
        body += `<div class="legend"><span><i class="lg free"></i>${t.free}</span><span><i class="lg mine"></i>${t.mine}</span><span><i class="lg taken"></i>${t.taken}</span></div>`;
      }

      const dlg = this._dialog ? (() => {
        const { kind, date, slot } = this._dialog;
        const time = data && data.times[slot] ? data.times[slot].join('–') : '';
        return `<div class="overlay" data-close="1"><div class="dialog" role="dialog" aria-modal="true">
            <div class="dicon ${kind}">${kind === 'book' ? ICON.plus : ICON.minus}</div>
            <h3>${kind === 'book' ? t.bookQ : t.cancelQ}</h3>
            <p>${esc(this._dayLabel(date))}${time ? ' · ' + time : ''}</p>
            <div class="dbtns"><button class="btn ghost" data-close="1">${t.close}</button>
            <button class="btn ${kind === 'cancel' ? 'danger' : ''}" data-confirm="1">${kind === 'book' ? t.book : t.cancel}</button></div>
          </div></div>`;
      })() : '';

      const toast = this._toast ? `<div class="toast${this._toast.error ? ' err' : ''}">${esc(this._toast.text)}</div>` : '';

      this.shadowRoot.innerHTML = `<style>${CSS}</style>
        <ha-card class="${narrow ? 'narrow' : 'wide'}">
          <div class="head">
            <div class="ic">${ICON.washer}</div>
            <div class="ttl">${esc(title)}</div>
            ${narrow ? '' : nav}
            <button class="nav refresh${this._busy === 'refresh' ? ' spinning' : ''}" data-refresh="1" aria-label="${t.refresh}" title="${t.refresh}">${ICON.refresh}</button>
          </div>
          ${narrow ? nav : ''}
          ${body}
          ${dlg}${toast}
        </ha-card>`;
      this._bind();
    }

    _bind() {
      const root = this.shadowRoot;
      root.querySelectorAll('[data-kind]').forEach((el) => {
        const open = () => { this._dialog = { kind: el.dataset.kind, date: el.dataset.date, slot: el.dataset.slot }; this._render(); };
        el.addEventListener('click', open);
        el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
      });
      root.querySelectorAll('[data-week]').forEach((el) => el.addEventListener('click', () => { this._week += Number(el.dataset.week); this._render(); }));
      root.querySelectorAll('[data-nav]').forEach((el) => el.addEventListener('click', () => { this._day += Number(el.dataset.nav); this._render(); }));
      const r = root.querySelector('[data-refresh]');
      if (r) r.addEventListener('click', () => this._refresh());
      root.querySelectorAll('[data-close]').forEach((el) => el.addEventListener('click', (e) => {
        if (e.target === el) { this._dialog = null; this._render(); }
      }));
      const c = root.querySelector('[data-confirm]');
      if (c) c.addEventListener('click', () => { const d = this._dialog; this._call(d.kind, d.date, d.slot); });
    }
  }

  const CSS = `
    :host { display: block;
      --ll-bg: var(--lulebo-card-background, #1e2022); --ll-tile: var(--lulebo-tile-background, #141414);
      --ll-text: var(--lulebo-text-color, #ffffff); --ll-muted: var(--lulebo-muted-color, #7d8083);
      --ll-accent: var(--lulebo-accent-color, #38f2e9); --ll-on-accent: #0d0f10; --ll-red: #ff8a80;
      --ll-font: var(--lulebo-font, 'Poppins', var(--paper-font-body1_-_font-family, system-ui), sans-serif); }
    ha-card { display: block; position: relative; overflow: hidden; background: var(--ll-bg); color: var(--ll-text); font-family: var(--ll-font);
      border-radius: var(--ha-card-border-radius, 24px); border: none; box-shadow: none; padding: 16px; box-sizing: border-box; }
    svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; display: block; }
    button { font: inherit; color: inherit; }
    .head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
    .ic { width: 42px; height: 42px; border-radius: 14px; background: var(--ll-tile); display: grid; place-items: center; color: var(--ll-accent); flex: none; }
    .ic svg { width: 22px; height: 22px; stroke-width: 1.8; }
    .ttl { font-size: 17px; font-weight: 500; flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .nav { appearance: none; border: 0; background: var(--ll-tile); color: var(--ll-text); width: 36px; height: 36px; border-radius: 50%;
      display: grid; place-items: center; cursor: pointer; flex: none; transition: background .15s; }
    .nav:hover:not([disabled]) { background: #24272a; }
    .nav[disabled] { opacity: .3; cursor: default; }
    .refresh svg { width: 18px; height: 18px; }
    .spinning svg { animation: spin 1s linear infinite; }
    .weeknav { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--ll-muted); }
    .weeknav span { min-width: 62px; text-align: center; }
    .daynav { display: grid; grid-template-columns: 40px 1fr 40px; align-items: center; gap: 8px; margin: 0 0 12px; }
    .daynav .nav { width: 40px; height: 40px; }
    .dayname { text-align: center; line-height: 1.2; }
    .dayname b { display: block; font-size: 18px; font-weight: 600; letter-spacing: -0.01em; }
    .dayname span { font-size: 12px; color: var(--ll-muted); }
    .next { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--ll-muted); background: var(--ll-tile); border-radius: 14px; padding: 10px 14px; margin: 0 0 12px; }
    .next b { color: var(--ll-text); font-weight: 500; }
    .next .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ll-muted); flex: none; }
    .next.has .dot { background: var(--ll-accent); box-shadow: 0 0 0 3px rgba(56,242,233,.18); }
    .grid { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 6px; }
    .dh { text-align: center; padding: 2px 0 6px; line-height: 1.15; }
    .dh span { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--ll-muted); }
    .dh b { font-size: 18px; font-weight: 400; }
    .dh.today span, .dh.today b { color: var(--ll-accent); }
    .dh.today b { font-weight: 600; }
    .tile { position: relative; border-radius: 14px; background: var(--ll-tile); min-height: 100px; padding: 10px 8px 8px; box-sizing: border-box;
      display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 2px; text-align: center; user-select: none;
      transition: transform .12s ease, background .15s ease, box-shadow .15s ease; }
    .tile .time { font-size: 13px; font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.2; }
    .tile .end { display: block; font-size: 11px; font-weight: 400; color: var(--ll-muted); }
    .tile .lbl { font-size: 10px; color: var(--ll-muted); text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }
    .tile .act { margin-top: auto; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; }
    .tile .act svg { width: 16px; height: 16px; stroke-width: 2.4; }
    .tile[role="button"] { cursor: pointer; }
    .tile[role="button"]:active { transform: scale(.97); }
    .tile:focus-visible { outline: 2px solid var(--ll-accent); outline-offset: 2px; }
    .tile.free { background: #24282b; }
    .tile.free:hover { background: #2a2f32; }
    .tile.free .lbl { color: var(--ll-accent); }
    .tile.free .act { background: rgba(56,242,233,.14); color: var(--ll-accent); }
    .tile.mine, .tile.now { background: linear-gradient(160deg, rgba(56,242,233,.30) 0%, rgba(56,242,233,.10) 100%); box-shadow: inset 0 0 0 1.5px var(--ll-accent); }
    .tile.mine .lbl, .tile.now .lbl { color: var(--ll-accent); font-weight: 600; }
    .tile.mine .act { background: var(--ll-accent); color: var(--ll-on-accent); }
    .tile.mine .end, .tile.now .end { color: rgba(255,255,255,.75); }
    .tile.taken .time { color: var(--ll-muted); }
    .tile.past { opacity: .38; }
    .tile.past .time { color: var(--ll-muted); }
    .tile.busy { pointer-events: none; }
    .list { display: flex; flex-direction: column; gap: 8px; }
    .tile.row { flex-direction: row; align-items: center; justify-content: space-between; text-align: left; min-height: 64px; padding: 12px 12px 12px 16px; }
    .tile.row .tt { display: flex; flex-direction: column; gap: 2px; }
    .tile.row .time { font-size: 17px; font-weight: 500; }
    .tile.row .dash { color: var(--ll-muted); margin: 0 4px; font-weight: 300; }
    .tile.row .lbl { margin: 0; font-size: 11px; }
    .tile.row .act, .tile.row.free .act, .tile.row.mine .act { margin: 0; width: auto; height: auto; border-radius: 0; background: none; }
    .pill { display: inline-flex; align-items: center; height: 36px; padding: 0 18px; border-radius: 999px; background: var(--ll-accent); color: var(--ll-on-accent);
      font-size: 13px; font-weight: 600; }
    .pill.ghost { background: rgba(13,15,16,.35); color: var(--ll-text); box-shadow: inset 0 0 0 1.5px rgba(255,255,255,.35); }
    .legend { display: flex; gap: 16px; justify-content: center; margin-top: 12px; font-size: 11px; color: var(--ll-muted); flex-wrap: wrap; }
    .legend span { display: inline-flex; align-items: center; gap: 6px; }
    .lg { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
    .lg.free { background: #2a2f32; box-shadow: inset 0 0 0 1.5px rgba(56,242,233,.6); }
    .lg.mine { background: var(--ll-accent); }
    .lg.taken { background: var(--ll-tile); box-shadow: inset 0 0 0 1px rgba(255,255,255,.12); }
    .empty { padding: 24px 8px; text-align: center; color: var(--ll-muted); font-size: 14px; }
    .spin { width: 20px; height: 20px; border-radius: 50%; border: 2.5px solid rgba(56,242,233,.25); border-top-color: var(--ll-accent);
      animation: spin .8s linear infinite; margin-top: auto; }
    .tile.row .spin { margin: 0 8px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .overlay { position: absolute; inset: 0; background: rgba(13,15,16,.72); -webkit-backdrop-filter: blur(4px); backdrop-filter: blur(4px);
      display: grid; place-items: center; padding: 16px; z-index: 5; animation: fade .15s ease; }
    .dialog { background: #191b1d; border-radius: 22px; padding: 22px 20px 16px; width: min(340px, 100%); text-align: center;
      box-shadow: 0 18px 40px rgba(0,0,0,.5), inset 0 0 0 1px rgba(255,255,255,.05); animation: pop .18s ease; }
    .dicon { width: 48px; height: 48px; border-radius: 16px; margin: 0 auto 10px; display: grid; place-items: center; }
    .dicon.book { background: rgba(56,242,233,.14); color: var(--ll-accent); }
    .dicon.cancel { background: rgba(255,138,128,.14); color: var(--ll-red); }
    .dialog h3 { margin: 0 0 4px; font-size: 18px; font-weight: 600; }
    .dialog p { margin: 0 0 18px; font-size: 14px; color: var(--ll-muted); }
    .dbtns { display: flex; gap: 8px; }
    .btn { flex: 1; appearance: none; border: 0; border-radius: 999px; height: 44px; font-weight: 600; font-size: 14px; cursor: pointer;
      background: var(--ll-accent); color: var(--ll-on-accent); }
    .btn.ghost { background: var(--ll-tile); color: var(--ll-text); }
    .btn.danger { background: var(--ll-red); color: var(--ll-on-accent); }
    .toast { position: absolute; left: 50%; bottom: 14px; transform: translateX(-50%); background: #2a2d30; color: var(--ll-text);
      padding: 10px 16px; border-radius: 999px; font-size: 13px; box-shadow: 0 10px 24px rgba(0,0,0,.45); max-width: calc(100% - 32px);
      z-index: 6; animation: fade .2s ease; text-align: center; }
    .toast.err { background: var(--ll-red); color: var(--ll-on-accent); }
    @keyframes fade { from { opacity: 0; } }
    @keyframes pop { from { transform: scale(.94); opacity: 0; } }
    @media (prefers-reduced-motion: reduce) { .overlay, .dialog, .toast, .spin, .spinning svg { animation: none; } }
  `;

  if (!customElements.get('lulebo-laundry-card')) customElements.define('lulebo-laundry-card', LuleboLaundryCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === 'lulebo-laundry-card')) {
    window.customCards.push({ type: 'lulebo-laundry-card', name: 'Lulebo Tvättstuga', description: 'Boka och avboka tvättider (vecka eller en dag i taget).', preview: false });
  }
  console.info(`%c LULEBO-LAUNDRY-CARD %c ${VERSION} `, 'background:#38f2e9;color:#0d0f10;font-weight:700', 'background:#1e2022;color:#fff');
})();
