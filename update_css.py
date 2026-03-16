import sys
import re

file_path = 'flask_book_recommendation/static/styles/luxury-theme.css'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

new_css = """/* ═══════════════════════════════════════════════════════
   🏛️ PREMIUM LUXURY MUSEUM BOOK CARDS (Ultra Beautiful)
   ═══════════════════════════════════════════════════════ */
.museum-book-card {
    background: linear-gradient(145deg, rgba(35, 28, 18, 0.4), rgba(15, 12, 8, 0.7)) !important;
    border: 1px solid rgba(201, 168, 76, 0.25) !important;
    border-radius: 16px !important;
    padding: 1.5rem 1rem 1.25rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    transition: all 0.5s cubic-bezier(0.25, 1, 0.5, 1) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    box-shadow: 
        0 8px 32px rgba(0, 0, 0, 0.6),
        inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    width: 200px !important;
    position: relative !important;
    overflow: hidden !important;
}

/* Dynamic Glare Effect */
.museum-book-card::before {
    content: '' !important;
    position: absolute !important;
    top: 0 !important; left: -100% !important;
    width: 50% !important; height: 100% !important;
    background: linear-gradient(to right, transparent, rgba(201, 168, 76, 0.15), transparent) !important;
    transform: skewX(-25deg) !important;
    transition: left 0.7s ease !important;
    z-index: 1 !important;
    pointer-events: none !important;
}

/* Light Mode Overrides */
[data-theme="light"] .museum-book-card {
    background: linear-gradient(145deg, rgba(255, 250, 240, 0.8), rgba(240, 235, 222, 0.95)) !important;
    border-color: rgba(184, 140, 60, 0.3) !important;
    box-shadow: 
        0 8px 32px rgba(0, 0, 0, 0.1),
        inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
}

.museum-book-card:hover {
    border-color: rgba(201, 168, 76, 0.6) !important;
    box-shadow: 
        0 15px 45px rgba(0, 0, 0, 0.8), 
        0 0 30px rgba(201, 168, 76, 0.25),
        inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
    transform: translateY(-8px) scale(1.02) !important;
}

.museum-book-card:hover::before {
    left: 200% !important;
}

[data-theme="light"] .museum-book-card:hover {
    box-shadow: 
        0 15px 45px rgba(0, 0, 0, 0.15), 
        0 0 30px rgba(184, 140, 60, 0.2) !important;
}

/* The actual book sitting inside the card */
.museum-book-cover-wrap {
    position: relative !important;
    width: 140px !important;
    height: 210px !important;
    margin: 0 auto 1.5rem !important;
    border-radius: 6px !important;
    box-shadow: 
        0 15px 35px rgba(0, 0, 0, 0.8), 
        -2px 0 10px rgba(0,0,0,0.5) inset !important;
    transition: all 0.5s cubic-bezier(0.25, 1, 0.5, 1) !important;
    background: #0d0b08 !important;
    overflow: hidden !important;
    z-index: 2 !important;
}

/* Book Spine Visual */
.museum-book-cover-wrap::after {
    content: '' !important;
    position: absolute !important;
    left: 0; top: 0; bottom: 0;
    width: 5px !important;
    background: linear-gradient(to right, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0) 100%) !important;
    z-index: 3 !important;
    pointer-events: none !important;
}

.museum-book-card:hover .museum-book-cover-wrap {
    transform: perspective(800px) rotateY(-8deg) scale(1.05) translateY(-5px) !important;
    box-shadow: 
        20px 20px 40px rgba(0, 0, 0, 0.9), 
        0 0 0 1px var(--lux-gold), 
        0 0 30px rgba(201, 168, 76, 0.5) !important;
}

.museum-book-cover-wrap img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    border-radius: 4px !important;
    transition: filter 0.5s ease !important;
}

.museum-book-card:hover .museum-book-cover-wrap img {
    filter: brightness(1.1) contrast(1.05) !important;
}

/* Premium No-Cover Placeholder */
.card-no-cover {
    position: absolute !important;
    inset: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    background: linear-gradient(135deg, #1c1813 0%, #0d0b08 100%) !important;
    border: 1px solid rgba(201, 168, 76, 0.1) !important;
}

.no-cover-pattern {
    color: rgba(201, 168, 76, 0.3) !important;
    font-size: 3rem !important;
}

/* Card overlay for actions */
.museum-book-cover-wrap .card-overlay-glass {
    position: absolute !important;
    inset: 0 !important;
    background: linear-gradient(to top, rgba(15, 12, 8, 0.95) 0%, rgba(15, 12, 8, 0.5) 50%, transparent 100%) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    opacity: 0 !important;
    transition: opacity 0.4s ease !important;
    z-index: 4 !important;
}

.museum-book-cover-wrap:hover .card-overlay-glass {
    opacity: 1 !important;
    backdrop-filter: blur(2px) !important;
}

.overlay-actions {
    display: flex !important;
    gap: 0.75rem !important;
    transform: translateY(15px) !important;
    transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
}

.museum-book-cover-wrap:hover .overlay-actions {
    transform: translateY(0) !important;
}

/* Text Information */
.museum-book-info {
    text-align: center !important;
    width: 100% !important;
    z-index: 2 !important;
    position: relative !important;
}

.museum-book-title {
    font-family: var(--lux-font-display) !important;
    color: var(--lux-cream) !important;
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.02em !important;
    line-height: 1.35 !important;
    margin: 0 0 0.5rem 0 !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.8) !important;
    transition: color 0.3s ease !important;
}

.museum-book-card:hover .museum-book-title {
    color: var(--lux-gold-glow) !important;
}

[data-theme="light"] .museum-book-title {
    color: var(--lux-text-primary) !important;
    text-shadow: none !important;
}

.museum-book-author {
    color: var(--lux-gold) !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.05em !important;
    margin: 0 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    opacity: 0.9 !important;
}

[data-theme="light"] .museum-book-author {
    color: var(--lux-gold-dim) !important;
}

.museum-book-link {
    display: block !important;
    text-decoration: none !important;
    width: 100% !important;
}

/* Action button inside overlay */
.action-btn-glass {
    background: rgba(20, 16, 12, 0.8) !important;
    border: 1px solid rgba(201, 168, 76, 0.5) !important;
    color: var(--lux-gold-glow) !important;
    border-radius: 50px !important;
    padding: 0.6rem 1.2rem !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    transition: all 0.3s ease !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 0.4rem !important;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5) !important;
}

.action-btn-glass:hover {
    background: linear-gradient(135deg, var(--lux-gold) 0%, var(--lux-copper) 100%) !important;
    border-color: transparent !important;
    color: #0d0b10 !important;
    box-shadow: 0 6px 20px rgba(201, 168, 76, 0.4) !important;
    transform: scale(1.05) !important;
}

/* Stars Rating */
.card-rating-row {
    margin-top: 0.75rem !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 0.2rem !important;
    background: rgba(0, 0, 0, 0.3) !important;
    padding: 0.3rem 0.8rem !important;
    border-radius: 20px !important;
    border: 1px solid rgba(201, 168, 76, 0.1) !important;
    box-shadow: inset 0 2px 5px rgba(0,0,0,0.5) !important;
}

.star-icon.filled {
    color: var(--lux-gold) !important;
    filter: drop-shadow(0 0 3px rgba(201, 168, 76, 0.6)) !important;
}
"""

start_marker = r'/\* ═══════════════════════════════════════════════════════\s*🏛️ LUXURY MUSEUM BOOK CARDS\s*═══════════════════════════════════════════════════════ \*/'
end_marker = r'\.action-btn-glass:hover \{\s*background: rgba\(201, 168, 76, 0\.25\) !important;\s*border-color: var\(--lux-gold\) !important;\s*\}'

pattern = re.compile(start_marker + r'.*?' + end_marker, re.DOTALL)
if pattern.search(content):
    new_content = pattern.sub(new_css, content)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Successfully updated museum book cards CSS.')
else:
    print('Could not find the target block in CSS.')
