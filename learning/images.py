"""Image presence metadata only: never fetch or interpret image bytes."""
import hashlib

IMAGE_SCAN_JS = r'''(row, content) => {
    const visible=e=>e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
    const candidates=new Set([
        ...(content?.querySelectorAll('img') || []),
        ...row.querySelectorAll('[data-e2e="comment-image"] img, img[data-e2e="comment-image"], img[alt="评论图片"], .RDy3JwM0 > img.duf1cdUE')]);
    const images=[...candidates].filter(img=>visible(img) && !img.closest('a, button, .comment-item-avatar') &&
        img.closest('[data-e2e="comment-item"]')===row && !img.matches('.qz6Hz920') &&
        !/^\[[^\[\]\r\n]{1,40}\]$/.test(img.alt?.trim()||''));
    const keys=images.map(img=>{
        const src=img.currentSrc || img.getAttribute('src');
        if(!src) return null;
        try {const url=new URL(src, document.baseURI);
            return ['https:','http:'].includes(url.protocol) ? url.origin+url.pathname : null;
        } catch {return null;}
    }).filter(Boolean);
    return {image_count:images.length, image_keys:keys};
}'''


def image_fields(raw):
    if not raw.get('image_count'):
        return {}
    return dict(content_status='image_not_read', image_count=raw['image_count'],
                image_fingerprints=[hashlib.sha256(key.encode()).hexdigest() for key in raw.get('image_keys', [])])


def image_identity(raw):
    if raw.get('text'):
        return raw['text']  # Preserve historical text IDs when adding presence metadata.
    fingerprints = image_fields(raw).get('image_fingerprints', [])
    return '\x00image:' + '|'.join(fingerprints) if fingerprints else ''


def placeholder_count(comments):
    return sum(c.get('content_status') == 'image_not_read' for c in comments)
