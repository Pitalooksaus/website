/* ========================================
   Belgian Websites — Admin Panel JS
   ========================================
   Open: Ctrl+Shift+A  of  ?admin in URL
   Wachtwoord: belgian2026
   ======================================== */

(function() {
    'use strict';

    // ============ CONFIG ============
    // Hash van het wachtwoord (SHA-256 van "belgian2026")
    // Je kunt dit veranderen door een nieuw wachtwoord te hashen
    const ADMIN_PASSWORD = 'belgian2026';
    const STORAGE_KEY = 'bw_leads';
    const SESSION_KEY = 'bw_admin_session';

    // ============ HELPERS ============
    function $(id) { return document.getElementById(id); }
    function $$(sel) { return document.querySelectorAll(sel); }

    function showToast(message, type = 'success') {
        const existing = document.querySelector('.admin-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = `admin-toast admin-toast--${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    // ============ LEAD STORAGE ============
    const LeadDB = {
        getAll() {
            try {
                return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            } catch { return []; }
        },

        save(leads) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(leads));
        },

        add(lead) {
            const leads = this.getAll();
            // Duplicate check
            const exists = leads.some(l =>
                l.name.toLowerCase() === lead.name.toLowerCase() &&
                l.city.toLowerCase() === lead.city.toLowerCase()
            );
            if (exists) return false;

            lead.id = Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
            lead.addedDate = new Date().toISOString();
            lead.status = lead.status || 'new';
            leads.push(lead);
            this.save(leads);
            return true;
        },

        update(id, updates) {
            const leads = this.getAll();
            const idx = leads.findIndex(l => l.id === id);
            if (idx !== -1) {
                leads[idx] = { ...leads[idx], ...updates };
                this.save(leads);
                return true;
            }
            return false;
        },

        delete(id) {
            const leads = this.getAll().filter(l => l.id !== id);
            this.save(leads);
        },

        filter(opts = {}) {
            let leads = this.getAll();
            if (opts.opportunity) leads = leads.filter(l => l.opportunity === opts.opportunity);
            if (opts.status) leads = leads.filter(l => l.status === opts.status);
            if (opts.city) leads = leads.filter(l => l.city.toLowerCase().includes(opts.city.toLowerCase()));
            return leads;
        }
    };

    // ============ WEBSITE CHECKER ============
    const WebsiteChecker = {
        async check(url) {
            if (!url || url.trim() === '') {
                return {
                    exists: false, url: null, score: 0,
                    issues: ['❌ Geen website gevonden'],
                    opportunity: 'HIGH'
                };
            }

            url = url.trim();
            if (!url.startsWith('http')) url = 'https://' + url;

            const result = {
                exists: false, url, score: 0, issues: [],
                opportunity: 'NONE', loadTime: null, hasSSL: url.startsWith('https')
            };

            try {
                const startTime = performance.now();

                // Use a CORS proxy or direct fetch
                // Note: many sites block direct browser requests, so we do what we can
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 10000);

                let response;
                try {
                    response = await fetch(url, {
                        method: 'HEAD',
                        mode: 'no-cors',
                        signal: controller.signal
                    });
                } catch(e) {
                    // no-cors mode — if it didn't throw, the site likely exists
                }

                clearTimeout(timeout);
                const loadTime = ((performance.now() - startTime) / 1000).toFixed(2);

                // Since we can't read the response in no-cors mode,
                // we'll do a basic analysis based on what we know
                result.exists = true;
                result.loadTime = parseFloat(loadTime);

                let score = 50; // Base score — we can't fully analyze in browser
                let issues = [];

                // Check SSL
                if (!url.startsWith('https')) {
                    score -= 15;
                    issues.push('❌ Geen HTTPS/SSL beveiliging');
                }

                // Check response time
                if (result.loadTime > 5) {
                    score -= 20;
                    issues.push(`🐌 Trage reactietijd (${loadTime}s)`);
                } else if (result.loadTime > 3) {
                    score -= 10;
                    issues.push(`⚠️ Matige reactietijd (${loadTime}s)`);
                } else {
                    score += 10;
                }

                // Try to fetch via CORS proxy for deeper analysis
                try {
                    const proxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`;
                    const proxyResp = await fetch(proxyUrl, { signal: AbortSignal.timeout(8000) });
                    const html = (await proxyResp.text()).toLowerCase();

                    // Check viewport (mobile responsive)
                    if (!html.includes('viewport')) {
                        score -= 25;
                        issues.push('📱 Niet mobiel-vriendelijk (geen viewport meta tag)');
                    } else {
                        score += 10;
                    }

                    // Check meta description
                    if (!html.includes('meta') || !html.includes('description')) {
                        score -= 10;
                        issues.push('🔍 Geen meta description (slecht voor SEO)');
                    }

                    // Check title
                    if (!html.includes('<title>') || html.includes('<title></title>')) {
                        score -= 10;
                        issues.push('🔍 Geen paginatitel');
                    }

                    // Check for placeholder
                    const placeholderTerms = ['coming soon', 'under construction', 'binnenkort', 'in opbouw', 'in aanbouw'];
                    if (placeholderTerms.some(t => html.includes(t))) {
                        score -= 30;
                        issues.push('🚧 Website is "in opbouw" of placeholder');
                    }

                    // Check modern design
                    const modernTerms = ['flex', 'grid', 'tailwind', 'bootstrap', 'react', 'vue', 'next'];
                    if (!modernTerms.some(t => html.includes(t))) {
                        score -= 10;
                        issues.push('🎨 Mogelijk verouderd design/technologie');
                    }

                    // Check if it's WordPress
                    if (html.includes('wp-content') || html.includes('wordpress')) {
                        issues.push('📝 WordPress website — mogelijk traag/verouderd');
                    }

                } catch(proxyErr) {
                    issues.push('ℹ️ Kon geen diepere analyse uitvoeren (CORS beperking)');
                }

                if (issues.length === 0) {
                    score = Math.min(score + 20, 100);
                }

                result.score = Math.max(0, Math.min(100, score));
                result.issues = issues;

                if (result.score < 30) result.opportunity = 'HIGH';
                else if (result.score < 60) result.opportunity = 'MEDIUM';
                else if (result.score < 80) result.opportunity = 'LOW';
                else result.opportunity = 'NONE';

            } catch (e) {
                result.issues = ['❌ Website niet bereikbaar of bestaat niet'];
                result.opportunity = 'HIGH';
                result.score = 0;
            }

            return result;
        }
    };

    // ============ OUTREACH TEMPLATES ============
    const OutreachTemplates = {
        no_website: {
            subject: (l) => `Website voor ${l.name}? 🚀`,
            message: (l) => `Beste ${l.name},

Ik kwam ${l.name} tegen in ${l.city} en merkte op dat jullie nog geen website hebben.
In 2026 zoekt meer dan 80% van de klanten online voordat ze een lokaal bedrijf bezoeken.

Bij Belgian Websites bouwen we professionele, moderne websites speciaal voor lokale bedrijven zoals die van jullie.

✅ Volledig op maat gemaakt
✅ Mobiel-vriendelijk
✅ Klaar binnen 7 dagen
✅ Vanaf €249

Zullen we eens vrijblijvend bespreken wat een website voor ${l.name} kan betekenen?

Groeten,
Belgian Websites
belgianwebsites@gmail.com`
        },

        bad_website: {
            subject: (l) => `Kleine tip voor de website van ${l.name} 💡`,
            message: (l) => `Beste ${l.name},

Ik bekeek de website van ${l.name} (${l.website || 'jullie website'}) en zag een paar verbeterpunten:

${(l.issues || []).map(i => '  • ' + i).join('\n')}

Een moderne, snelle website kan een groot verschil maken voor jullie online vindbaarheid en klantenaantal.

Bij Belgian Websites helpen we lokale bedrijven in ${l.city} met het verbeteren of opnieuw bouwen van hun website.

Wil je weten wat we voor ${l.name} kunnen doen? Ik maak graag een gratis analyse!

Groeten,
Belgian Websites
belgianwebsites@gmail.com`
        },

        placeholder_website: {
            subject: (l) => `Hulp met de website van ${l.name}? 🛠️`,
            message: (l) => `Beste ${l.name},

Ik zag dat de website van ${l.name} momenteel nog in aanbouw is.
Mocht je hulp nodig hebben om die snel af te ronden, dan kan ik je helpen!

Bij Belgian Websites bouwen we complete websites voor lokale bedrijven in ${l.city}:
- Professioneel design op maat
- Klaar binnen 7 dagen
- Alles geregeld (design, hosting, SEO)

Interesse in een vrijblijvend gesprek?

Groeten,
Belgian Websites
belgianwebsites@gmail.com`
        },

        instagram_dm: {
            subject: () => null,
            message: (l) => `Hey ${l.name}! 👋

Ik zag jullie profiel en het ziet er goed uit! 🔥
Maar ik merkte dat jullie nog geen website hebben.

Wist je dat 80% van de klanten eerst online zoekt? Een professionele website kan jullie echt helpen meer klanten te krijgen.

Ik bouw websites speciaal voor lokale bedrijven in ${l.city}, vanaf €249.

Interesse? Stuur gerust een berichtje! 😊
belgianwebsites@gmail.com`
        }
    };

    function generateOutreach(lead, templateKey) {
        if (templateKey === 'auto') {
            if (!lead.website) templateKey = 'no_website';
            else if (lead.opportunity === 'HIGH') templateKey = 'bad_website';
            else if ((lead.issues || []).some(i => i.toLowerCase().includes('opbouw'))) templateKey = 'placeholder_website';
            else templateKey = 'no_website';
        }

        const template = OutreachTemplates[templateKey];
        if (!template) return null;

        return {
            subject: template.subject(lead),
            message: template.message(lead)
        };
    }

    // ============ UI RENDERING ============
    function renderDashboard() {
        const leads = LeadDB.getAll();
        const high = leads.filter(l => l.opportunity === 'HIGH').length;
        const medium = leads.filter(l => l.opportunity === 'MEDIUM').length;
        const contacted = leads.filter(l => l.status === 'contacted' || l.status === 'interested' || l.status === 'closed').length;

        $('statTotal').textContent = leads.length;
        $('statHigh').textContent = high;
        $('statMedium').textContent = medium;
        $('statContacted').textContent = contacted;

        // Hot leads table
        const hotLeads = leads.filter(l => l.opportunity === 'HIGH' && l.status === 'new');
        const hotBody = $('hotLeadsTable').querySelector('tbody');
        hotBody.innerHTML = '';
        $('hotLeadsEmpty').style.display = hotLeads.length ? 'none' : 'block';

        hotLeads.slice(0, 15).forEach(l => {
            hotBody.innerHTML += createLeadRow(l, false);
        });
    }

    function renderLeadsTable() {
        const oppFilter = $('filterOpportunity').value;
        const statusFilter = $('filterStatus').value;
        const leads = LeadDB.filter({ opportunity: oppFilter || undefined, status: statusFilter || undefined });

        const body = $('allLeadsTable').querySelector('tbody');
        body.innerHTML = '';
        $('allLeadsEmpty').style.display = leads.length ? 'none' : 'block';

        leads.forEach(l => {
            body.innerHTML += createLeadRow(l, true);
        });
    }

    function createLeadRow(lead, showWebsite) {
        const oppClass = { HIGH: 'high', MEDIUM: 'medium', LOW: 'low' }[lead.opportunity] || '';
        const oppLabel = { HIGH: '🔴 Hoog', MEDIUM: '🟡 Medium', LOW: '🟢 Laag' }[lead.opportunity] || '-';
        const statusLabel = { new: 'Nieuw', contacted: 'Gecontacteerd', interested: 'Geïnteresseerd', closed: 'Afgesloten' }[lead.status] || lead.status;
        const statusClass = lead.status !== 'new' ? `status-badge--${lead.status}` : '';

        const websiteCols = showWebsite ? `
            <td>${lead.website ? `<a href="${lead.website}" target="_blank" style="color:var(--accent)">${new URL(lead.website).hostname}</a>` : '<span style="color:var(--text-tertiary)">—</span>'}</td>
            <td>${lead.score !== undefined ? lead.score + '/100' : '—'}</td>
        ` : '';

        return `<tr>
            <td>${lead.name}</td>
            <td>${lead.type || '—'}</td>
            <td>${lead.city || '—'}</td>
            ${websiteCols}
            <td><span class="opp-badge opp-badge--${oppClass}">${oppLabel}</span></td>
            <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
            <td>
                <button class="admin-action-btn" onclick="window._adminActions.message('${lead.id}')">📧</button>
                <button class="admin-action-btn" onclick="window._adminActions.toggleStatus('${lead.id}')">✅</button>
                <button class="admin-action-btn admin-action-btn--danger" onclick="window._adminActions.deleteLead('${lead.id}')">🗑️</button>
            </td>
        </tr>`;
    }

    function renderOutreachSelect() {
        const select = $('outreachLead');
        const leads = LeadDB.getAll();
        select.innerHTML = '<option value="">Kies een lead...</option>';
        leads.forEach(l => {
            const emoji = { HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢' }[l.opportunity] || '⚪';
            select.innerHTML += `<option value="${l.id}">${emoji} ${l.name} (${l.city})</option>`;
        });
    }

    // ============ ACTIONS ============
    window._adminActions = {
        message(id) {
            const lead = LeadDB.getAll().find(l => l.id === id);
            if (!lead) return;

            // Switch to outreach tab
            switchTab('outreach');
            $('outreachLead').value = id;
            $('generateOutreach').click();
        },

        toggleStatus(id) {
            const lead = LeadDB.getAll().find(l => l.id === id);
            if (!lead) return;

            const statusCycle = ['new', 'contacted', 'interested', 'closed'];
            const currentIdx = statusCycle.indexOf(lead.status);
            const nextStatus = statusCycle[(currentIdx + 1) % statusCycle.length];

            LeadDB.update(id, { status: nextStatus });
            showToast(`Status gewijzigd naar: ${nextStatus}`);
            renderDashboard();
            renderLeadsTable();
        },

        deleteLead(id) {
            if (confirm('Weet je zeker dat je deze lead wilt verwijderen?')) {
                LeadDB.delete(id);
                showToast('Lead verwijderd', 'error');
                renderDashboard();
                renderLeadsTable();
                renderOutreachSelect();
            }
        }
    };

    // ============ TAB SWITCHING ============
    function switchTab(tabName) {
        $$('.admin-tab-btn').forEach(btn => btn.classList.remove('active'));
        $$('.admin-tab').forEach(tab => tab.classList.remove('active'));

        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
        $(`tab-${tabName}`).classList.add('active');

        if (tabName === 'dashboard') renderDashboard();
        if (tabName === 'leads') renderLeadsTable();
        if (tabName === 'outreach') renderOutreachSelect();
    }

    // ============ INIT ============
    function initAdmin() {
        const overlay = $('adminOverlay');
        const loginForm = $('adminLoginForm');
        const dashboard = $('adminDashboard');
        const login = $('adminLogin');

        // --- Link admin CSS ---
        if (!document.querySelector('link[href="admin.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = 'admin.css';
            document.head.appendChild(link);
        }

        // --- Open admin panel ---
        function openAdmin() {
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';

            // Check if already authenticated this session
            if (sessionStorage.getItem(SESSION_KEY) === 'true') {
                login.style.display = 'none';
                dashboard.style.display = 'flex';
                renderDashboard();
            } else {
                login.style.display = 'flex';
                dashboard.style.display = 'none';
                setTimeout(() => $('adminPassword').focus(), 100);
            }
        }

        function closeAdmin() {
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }

        // Keyboard shortcut: Ctrl+Shift+A
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.shiftKey && e.key === 'A') {
                e.preventDefault();
                openAdmin();
            }
            if (e.key === 'Escape' && overlay.classList.contains('active')) {
                closeAdmin();
            }
        });

        // URL parameter: ?admin
        if (window.location.search.includes('admin')) {
            openAdmin();
        }

        // Close button
        $('adminClose').addEventListener('click', closeAdmin);

        // --- Login ---
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const pwd = $('adminPassword').value;

            if (pwd === ADMIN_PASSWORD) {
                sessionStorage.setItem(SESSION_KEY, 'true');
                login.style.display = 'none';
                dashboard.style.display = 'flex';
                $('adminError').textContent = '';
                renderDashboard();
                showToast('✅ Welkom, admin!');
            } else {
                $('adminError').textContent = '❌ Verkeerd wachtwoord';
                $('adminPassword').value = '';
                $('adminPassword').focus();
            }
        });

        // --- Tab switching ---
        $$('.admin-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.tab));
        });

        // --- Website Checker ---
        $('checkerBtn').addEventListener('click', async () => {
            const url = $('checkerUrl').value.trim();
            if (!url) {
                showToast('Voer een URL in', 'error');
                return;
            }

            const btn = $('checkerBtn');
            btn.innerHTML = '<span>Analyseren...</span>';
            btn.disabled = true;

            const result = await WebsiteChecker.check(url);

            btn.innerHTML = '<span>Analyseer</span>';
            btn.disabled = false;

            // Show result
            $('checkerResult').style.display = 'flex';

            // Animate score ring
            const circle = $('checkerScoreCircle');
            const circumference = 327;
            const offset = circumference - (result.score / 100) * circumference;

            const color = result.score >= 70 ? '#2dd4a8' : result.score >= 40 ? '#f7a80d' : '#e84057';
            circle.style.stroke = color;
            circle.style.transition = 'stroke-dashoffset 1s ease-out';
            setTimeout(() => { circle.style.strokeDashoffset = offset; }, 50);

            // Score number
            let currentScore = 0;
            const scoreEl = $('checkerScoreNum');
            const scoreInterval = setInterval(() => {
                currentScore += Math.ceil(result.score / 30);
                if (currentScore >= result.score) {
                    currentScore = result.score;
                    clearInterval(scoreInterval);
                }
                scoreEl.textContent = currentScore;
                scoreEl.style.color = color;
            }, 30);

            // Opportunity text
            const oppTexts = {
                HIGH: '🔴 Hoge kans — Dit bedrijf heeft jullie nodig!',
                MEDIUM: '🟡 Medium kans — Website kan beter',
                LOW: '🟢 Lage kans — Website is redelijk',
                NONE: '✅ Geen kans — Website is goed'
            };
            $('checkerOpp').textContent = oppTexts[result.opportunity];
            $('checkerOpp').style.color = color;

            // Issues
            const issuesList = $('checkerIssues');
            issuesList.innerHTML = '';
            result.issues.forEach(issue => {
                issuesList.innerHTML += `<li>${issue}</li>`;
            });
        });

        // --- Add Lead Form ---
        $('addLeadForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const website = $('leadWebsite').value.trim();
            let websiteData = { score: 0, issues: ['❌ Geen website'], opportunity: 'HIGH' };

            if (website) {
                websiteData = await WebsiteChecker.check(website);
            }

            const lead = {
                name: $('leadName').value.trim(),
                type: $('leadType').value.trim(),
                city: $('leadCity').value.trim(),
                website: website || '',
                contact: $('leadContact').value.trim(),
                score: websiteData.score,
                issues: websiteData.issues,
                opportunity: websiteData.opportunity,
            };

            if (LeadDB.add(lead)) {
                showToast(`✅ ${lead.name} toegevoegd als lead!`);
                $('addLeadForm').reset();
                renderDashboard();
                renderLeadsTable();
            } else {
                showToast('⚠️ Dit bedrijf bestaat al in de database', 'error');
            }
        });

        // --- Filters ---
        $('filterOpportunity').addEventListener('change', renderLeadsTable);
        $('filterStatus').addEventListener('change', renderLeadsTable);

        // --- Export CSV ---
        $('exportCsvBtn').addEventListener('click', () => {
            const leads = LeadDB.getAll();
            if (!leads.length) {
                showToast('Geen leads om te exporteren', 'error');
                return;
            }

            const headers = ['Naam', 'Type', 'Stad', 'Website', 'Score', 'Kans', 'Status', 'Contact', 'Datum'];
            const rows = leads.map(l => [
                l.name, l.type, l.city, l.website || '', l.score || 0,
                l.opportunity, l.status, l.contact || '', l.addedDate || ''
            ]);

            let csv = '\uFEFF'; // BOM for Excel
            csv += headers.join(';') + '\n';
            rows.forEach(row => {
                csv += row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(';') + '\n';
            });

            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `leads_${new Date().toISOString().slice(0,10)}.csv`;
            link.click();

            showToast(`✅ ${leads.length} leads geëxporteerd!`);
        });

        // --- Outreach Generator ---
        $('generateOutreach').addEventListener('click', () => {
            const leadId = $('outreachLead').value;
            const templateKey = $('outreachTemplate').value;

            if (!leadId) {
                showToast('Selecteer eerst een lead', 'error');
                return;
            }

            const lead = LeadDB.getAll().find(l => l.id === leadId);
            if (!lead) return;

            const outreach = generateOutreach(lead, templateKey);
            if (!outreach) {
                showToast('Kon geen bericht genereren voor deze lead', 'error');
                return;
            }

            $('outreachPreview').style.display = 'block';
            $('outreachSubject').textContent = outreach.subject ? `📌 ${outreach.subject}` : '(Geen onderwerp — DM bericht)';
            $('outreachBody').textContent = outreach.message;

            // Store current lead for mark contacted
            $('outreachPreview').dataset.leadId = leadId;
        });

        // Copy outreach
        $('copyOutreach').addEventListener('click', () => {
            const text = $('outreachBody').textContent;
            navigator.clipboard.writeText(text).then(() => {
                showToast('📋 Bericht gekopieerd!');
            }).catch(() => {
                // Fallback
                const textarea = document.createElement('textarea');
                textarea.value = text;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                textarea.remove();
                showToast('📋 Bericht gekopieerd!');
            });
        });

        // Mark as contacted
        $('markContacted').addEventListener('click', () => {
            const leadId = $('outreachPreview').dataset.leadId;
            if (leadId) {
                LeadDB.update(leadId, { status: 'contacted' });
                showToast('✅ Lead gemarkeerd als gecontacteerd');
                renderDashboard();
                renderLeadsTable();
            }
        });
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAdmin);
    } else {
        initAdmin();
    }

})();
