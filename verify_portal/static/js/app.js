// ============================================
// EPI LABS - Interactive Features (World-Class)
// ============================================

// Navigation scroll effect (for sticky header)
const nav = document.querySelector('.nav');
let lastScrollY = window.scrollY;

window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
        nav.classList.add('scrolled');
    } else {
        nav.classList.remove('scrolled');
    }
    lastScrollY = window.scrollY;
});

// Smooth scroll for anchor links (handling cross-page if needed or internal)
// Modified to work with multi-page structure
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        // Close mobile menu if open
        const hamburger = document.querySelector('.hamburger');
        const navLinks = document.querySelector('.nav-links');
        const navCta = document.querySelector('.nav-cta');

        if (hamburger && hamburger.classList.contains('active')) {
            hamburger.classList.remove('active');
            navLinks.classList.remove('active');
            if (navCta) navCta.classList.remove('active');
        }

        // Only prevent default if it's a hash link on the CURRENT page
        const href = this.getAttribute('href');
        if (href.startsWith('#')) {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        }
    });
});

// ============================================
// Scroll-Spy: Highlight Active Nav Link
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('.nav-links a');
    const sections = [];
    const currentPath = window.location.pathname.split('/').pop() || 'index.html';

    // Build a map of nav links to their target sections
    navLinks.forEach(link => {
        const href = link.getAttribute('href');

        // Handle same-page hash links (e.g., #get-started, index.html#get-started)
        if (href.includes('#')) {
            const [path, hash] = href.split('#');
            // Only track if it's for the current page or no path specified
            if (!path || path === currentPath || path === 'index.html') {
                const section = document.getElementById(hash);
                if (section) {
                    sections.push({ link, section, hash });
                }
            }
        }
    });

    // Function to update active link
    function updateActiveLink(activeHash = null) {
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            let shouldBeActive = false;

            if (activeHash && href.includes('#')) {
                // For hash links, check if the hash matches
                const [path, hash] = href.split('#');
                if (hash === activeHash && (!path || path === currentPath || path === 'index.html')) {
                    shouldBeActive = true;
                }
            } else if (!activeHash && !href.includes('#')) {
                // For non-hash links, check if page matches
                if (href === currentPath || href.includes(currentPath)) {
                    shouldBeActive = true;
                }
            }

            if (shouldBeActive) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    // IntersectionObserver for scroll-spy (only if we have sections to track)
    if (sections.length > 0) {
        const observerOptions = {
            root: null,
            rootMargin: '-20% 0px -75% 0px', // Trigger when section is in the top 25% of viewport
            threshold: 0
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // Find the section in our map
                    const activeSection = sections.find(s => s.section === entry.target);
                    if (activeSection) {
                        updateActiveLink(activeSection.hash);
                    }
                }
            });
        }, observerOptions);

        // Observe all sections
        sections.forEach(({ section }) => observer.observe(section));

        // Handle hash changes (when user clicks a link)
        window.addEventListener('hashchange', () => {
            const hash = window.location.hash.substring(1); // Remove #
            if (hash) {
                updateActiveLink(hash);
            }
        });

        // Initial highlight based on URL hash
        const initialHash = window.location.hash.substring(1);
        if (initialHash) {
            updateActiveLink(initialHash);
        } else {
            updateActiveLink(null); // Will highlight page-level link
        }
    } else {
        // No hash sections on this page, just highlight current page link
        updateActiveLink(null);
    }
});


// Hamburger menu toggle
const hamburger = document.querySelector('.hamburger');
const navLinksContainer = document.querySelector('.nav-links'); // Renamed to avoid specific conflict
const navCta = document.querySelector('.nav-cta');

if (hamburger) {
    hamburger.addEventListener('click', () => {
        hamburger.classList.toggle('active');
        navLinksContainer.classList.toggle('active');
        navCta.classList.toggle('active');
    });

    // Mobile Back Button logic
    const mobileBack = document.querySelector('.mobile-back');
    if (mobileBack) {
        mobileBack.addEventListener('click', () => {
            hamburger.classList.remove('active');
            navLinksContainer.classList.remove('active');
            navCta.classList.remove('active');
        });
    }
}

// ============================================
// FEATURE 1: Interactive Terminal Demo
// ============================================

class InteractiveTerminal {
    constructor(element) {
        this.element = element;
        this.input = element.querySelector('.terminal-input');
        this.output = element.querySelector('.terminal-output');
        this.prompt = element.querySelector('.terminal-prompt');

        if (!this.output) return; // Input might be absent in read-only terminals

        // If input exists, it's interactive
        if (this.input) {
            this.commands = {
                'epi verify sample.epi': this.verifyCommand.bind(this),
                'epi record script.py': this.recordCommand.bind(this),
                'help': this.helpCommand.bind(this),
                'clear': this.clearCommand.bind(this)
            };

            this.input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.executeCommand();
                }
            });
        }

        // Auto-type effect for demo purposes (if it has the typewriter class)
        // This is a simple visual effect to make the static demo look like it's being typed
        if (this.element.classList.contains('terminal-interactive')) {
            // Optional: Auto run a demo sequence if desired
        }
    }

    addOutput(text, type = 'normal') {
        const line = document.createElement('div');
        line.className = `terminal-line ${type}`;
        line.textContent = text;
        this.output.appendChild(line);
        this.output.scrollTop = this.output.scrollHeight;
    }

    // Typewriter effect for output
    // Usage: this.typeOutput("some text", "success", 20);
    typeOutput(text, type = 'normal', speed = 20) {
        const line = document.createElement('div');
        line.className = `terminal-line ${type}`;
        this.output.appendChild(line);
        this.output.scrollTop = this.output.scrollHeight;

        let i = 0;
        const typeChar = () => {
            if (i < text.length) {
                line.textContent += text.charAt(i);
                i++;
                setTimeout(typeChar, speed);
            }
        };
        typeChar();
    }

    executeCommand() {
        const command = this.input.value.trim();
        if (!command) return;

        this.addOutput(`$ ${command}`, 'command');

        if (this.commands[command]) {
            this.commands[command]();
        } else {
            this.addOutput(`Command not found: ${command}. Type 'help' for available commands.`, 'error');
        }

        this.input.value = '';
    }

    verifyCommand() {
        this.addOutput('... Loading sample.epi...', 'loading');
        setTimeout(() => {
            this.addOutput('OK Archive structure valid', 'success');
            this.addOutput('OK Manifest signature verified (Ed25519)', 'success');
            this.addOutput('OK All 47 step hashes match', 'success');
            setTimeout(() => {
                this.addOutput('OK Artifacts integrity confirmed', 'success');
                this.addOutput('', 'normal');
                this.addOutput('Reproducibility Score: 100%', 'highlight');
            }, 600);
        }, 800);
    }

    recordCommand() {
        this.addOutput('... Recording execution...', 'loading');
        setTimeout(() => {
            this.addOutput('Captured 23 steps', 'success');
            this.addOutput('Logged 5 OpenAI API calls', 'success');
            setTimeout(() => {
                this.addOutput('Created 3 artifacts', 'success');
                this.addOutput('', 'normal');
                this.addOutput('OK Saved to output.epi (signed)', 'highlight');
            }, 500);
        }, 1000);
    }

    helpCommand() {
        this.addOutput('Available commands (v2.0 - Production Ready):', 'normal');
        this.addOutput('  epi verify sample.epi  - Verify .epi file integrity', 'info');
        this.addOutput('  epi record script.py   - Record Python execution', 'info');
        this.addOutput('  clear                  - Clear terminal', 'info');
        this.addOutput('', 'normal');
        this.addOutput('Note: Replay feature coming in v2.1', 'info');
    }

    clearCommand() {
        this.output.innerHTML = '';
    }
}

// Initialize interactive terminals
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.terminal-interactive').forEach(terminal => {
        new InteractiveTerminal(terminal);
    });
});

// ============================================
// FEATURE 2: Hover Tilt Effects
// ============================================

class TiltEffect {
    constructor(element) {
        this.element = element;
        this.boundingRect = element.getBoundingClientRect();

        element.addEventListener('mousemove', this.handleMouseMove.bind(this));
        element.addEventListener('mouseleave', this.handleMouseLeave.bind(this));
    }

    handleMouseMove(e) {
        const rect = this.element.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        const rotateX = ((y - centerY) / centerY) * -10;
        const rotateY = ((x - centerX) / centerX) * 10;

        this.element.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
    }

    handleMouseLeave() {
        this.element.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
    }
}

// Apply tilt effect to cards
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.crisis-card, .lifecycle-step, .use-case-card, .vision-tier').forEach(card => {
        card.style.transition = 'transform 0.3s ease';
        new TiltEffect(card);
    });
});

// ============================================
// FEATURE 3: Animated Stats Count-Up
// ============================================

class CountUp {
    constructor(element, start, end, duration = 2000) {
        this.element = element;
        this.start = start;
        this.end = end;
        this.duration = duration;
        this.hasAnimated = false;
    }

    animate() {
        if (this.hasAnimated) return;
        this.hasAnimated = true;

        const startTime = performance.now();
        const step = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / this.duration, 1);

            const easeOutQuart = 1 - Math.pow(1 - progress, 4);
            const current = Math.floor(this.start + (this.end - this.start) * easeOutQuart);

            this.element.textContent = this.formatNumber(current);

            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                this.element.textContent = this.formatNumber(this.end);
            }
        };

        requestAnimationFrame(step);
    }

    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M+';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(0) + 'K+';
        }
        return num.toString();
    }
}

// Initialize count-up animations
const statObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting && entry.target.dataset.countup) {
            const counter = new CountUp(
                entry.target,
                0,
                parseInt(entry.target.dataset.countup),
                2000
            );
            counter.animate();
            statObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.5 });

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-countup]').forEach(stat => {
        statObserver.observe(stat);
    });
});

// ============================================
// FEATURE 4: Code Block Copy Animation
// ============================================

function createCopyButton(codeBlock) {
    const wrapper = document.createElement('div');
    wrapper.className = 'code-block-wrapper'; // Ensure this class is in CSS

    // If current parent is already a wrapper (e.g. from previous runs), skip
    if (codeBlock.parentElement.classList.contains('code-block-wrapper')) return;

    const button = document.createElement('button');
    button.className = 'copy-button';
    button.title = 'Copy to clipboard';
    button.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M5 2H11C11.5523 2 12 2.44772 12 3V5" stroke="currentColor" stroke-width="1.5"/>
            <rect x="4" y="5" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/>
        </svg>
    `;

    button.addEventListener('click', async () => {
        const code = codeBlock.textContent;
        await navigator.clipboard.writeText(code);

        button.classList.add('copied');
        button.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M3 8L6 11L13 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
        `;

        setTimeout(() => {
            button.classList.remove('copied');
            button.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M5 2H11C11.5523 2 12 2.44772 12 3V5" stroke="currentColor" stroke-width="1.5"/>
                    <rect x="4" y="5" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/>
                </svg>
            `;
        }, 2000);
    });

    // Insert wrapper before codeBlock
    codeBlock.parentNode.insertBefore(wrapper, codeBlock);
    // Move codeBlock into wrapper
    wrapper.appendChild(codeBlock);
    // Append button to wrapper
    wrapper.appendChild(button);
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.code-block code, .step-code code').forEach(codeBlock => {
        // Target the <code> element, but wrap the container if possible
        // Actually the original code wrapped the whole block. 
        // Here we'll wrap the parent div if it's the container, or just the code block.
        // Let's stick to the previous simple logic but robust
        // The HTML structure is usually <div class="step-code"><code>...</code></div>
        // So we want to wrap the <code> or put the button in the div.

        // Simpler approach: Append button to the parent container (.step-code or .code-block)
        // Check if parent has position: relative in CSS.
        const parent = codeBlock.parentElement;
        if (parent.classList.contains('step-code') || parent.classList.contains('code-block')) {
            if (parent.querySelector('.copy-button')) return; // already has one

            const button = document.createElement('button');
            button.className = 'copy-button';
            button.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M5 2H11C11.5523 2 12 2.44772 12 3V5" stroke="currentColor" stroke-width="1.5"/>
                    <rect x="4" y="5" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/>
                </svg>
            `;
            button.onclick = async () => {
                await navigator.clipboard.writeText(codeBlock.textContent);
                button.classList.add('copied');
                button.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8L6 11L13 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
                setTimeout(() => {
                    button.classList.remove('copied');
                    button.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M5 2H11C11.5523 2 12 2.44772 12 3V5" stroke="currentColor" stroke-width="1.5"/><rect x="4" y="5" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.5"/></svg>`;
                }, 2000);
            };
            parent.style.position = 'relative'; // ensure button positioning works
            parent.appendChild(button);
        }
    });
});

// ============================================
// Scroll reveal animation
// ============================================

const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('revealed');
        }
    });
}, observerOptions);

// Apply reveal animation to sections and cards
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.section, .crisis-card, .lifecycle-step, .use-case-card, .roadmap-item').forEach(el => {
        el.classList.add('reveal-on-scroll');
        observer.observe(el);
    });
});

// Parallax effect for hero section
window.addEventListener('scroll', () => {
    const hero = document.querySelector('.hero');
    if (hero) {
        const scrolled = window.scrollY;
        hero.style.transform = `translateY(${scrolled * 0.3}px)`;
        hero.style.opacity = 1 - (scrolled * 0.0015);
    }
});

// Initialize all animations on load
window.addEventListener('load', () => {
    document.body.classList.add('loaded');
});

// ============================================
// Contact Form - Opens User's Email Client
// ============================================

function sendEmail(event) {
    event.preventDefault();

    // Get form values
    const name = document.getElementById('name').value;
    const email = document.getElementById('email').value;
    const company = document.getElementById('company').value || 'Not specified';
    const inquiryType = document.getElementById('inquiry_type').value;
    const message = document.getElementById('message').value;

    // Create email subject
    const subject = encodeURIComponent('EPI LABS Inquiry: ' + inquiryType);

    // Create email body
    const body = encodeURIComponent(
        'Hello EPI LABS Team,\n\n' +
        '--- INQUIRY DETAILS ---\n\n' +
        'Name: ' + name + '\n' +
        'Email: ' + email + '\n' +
        'Company: ' + company + '\n' +
        'Inquiry Type: ' + inquiryType + '\n\n' +
        '--- MESSAGE ---\n\n' +
        message + '\n\n' +
        '---\n' +
        'Sent from EPI LABS Website Contact Form'
    );
    // Gmail compose URL - opens Gmail directly
    const gmailUrl = 'https://mail.google.com/mail/?view=cm&fs=1&to=mohdibrahim@epilabs.org&su=' + subject + '&body=' + body;
    window.open(gmailUrl, '_blank');

    // Optional: Clear form after a delay
    setTimeout(() => {
        document.getElementById('contactForm').reset();
    }, 1000);
}
