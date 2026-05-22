const initializeRankingBoard = (board) => {
    const pool = board.querySelector('[data-dropzone="pool"]');
    const bucketZones = Array.from(board.querySelectorAll('[data-dropzone="bucket"]'));
    const resetButton = board.querySelector('[data-action="reset"]');
    const finalizeButton = board.querySelector('[data-action="finalize"]');
    const downloadButton = board.querySelector('[data-action="download"]');
    const resultBody = board.querySelector('.ranking-result-body');
    const statusText = board.querySelector('.ranking-status');
    const placedCount = board.querySelector('.placed-count');
    const pageShell = board.closest('.page-shell');
    const completeUrl = pageShell ? pageShell.dataset.completeUrl : '';
    const modal = document.querySelector('[data-event-modal]');
    const modalTitle = modal ? modal.querySelector('[data-event-modal-title]') : null;
    const modalType = modal ? modal.querySelector('[data-event-modal-type]') : null;
    const modalDate = modal ? modal.querySelector('[data-event-modal-date]') : null;
    const modalDescription = modal ? modal.querySelector('[data-event-modal-description]') : null;
    const modalLocation = modal ? modal.querySelector('[data-event-modal-location]') : null;
    const modalTags = modal ? modal.querySelector('[data-event-modal-tags]') : null;
    const modalCloseButtons = modal ? Array.from(modal.querySelectorAll('[data-event-action="close-modal"]')) : [];

    // allow running without the separate result panel (ranking removed)
    if (!pool || bucketZones.length === 0) {
        return;
    }

    const initialOrder = Array.from(pool.querySelectorAll('.event-card')).map((card) => card.dataset.eventId);
    const cardsById = new Map(Array.from(board.querySelectorAll('.event-card')).map((card) => [card.dataset.eventId, card]));
    let draggedCard = null;
    let finalized = false;

    const escapeHtml = (value) => String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');

    const closeEventDetails = () => {
        if (!modal) {
            return;
        }

        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('has-event-modal');
    };

    const openEventDetails = (card) => {
        if (!card || finalized || !modal) {
            return;
        }

        if (modalTitle) modalTitle.textContent = card.dataset.eventName || 'Unbenanntes Event';
        if (modalType) modalType.textContent = card.dataset.eventType || 'Event';
        if (modalDate) modalDate.textContent = card.dataset.eventDate || 'ohne Datum';
        if (modalDescription) {
            const descriptionValue = card.dataset.eventDescription || '';

            try {
                modalDescription.textContent = descriptionValue ? JSON.parse(descriptionValue) : '';
            } catch {
                modalDescription.textContent = descriptionValue;
            }
        }
        if (modalLocation) modalLocation.textContent = card.dataset.eventLocation || 'Unbekannter Ort';
        if (modalTags) modalTags.textContent = (card.dataset.eventTags || '').split(', ').filter(Boolean).slice(0, 3).join(' · ');

        modal.hidden = false;
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('has-event-modal');
    };

    const allDropzones = [pool, ...bucketZones];

    const getBucketForCard = (card) => card.closest('[data-dropzone]');

    const updateCardStar = (card) => {
        const zone = getBucketForCard(card);
        card.dataset.star = zone && zone.dataset.star ? zone.dataset.star : '';
    };

    const updateAllCardStars = () => {
        board.querySelectorAll('.event-card').forEach(updateCardStar);
    };

    const getDragAfterElement = (container, clientX) => {
        const draggableElements = Array.from(container.querySelectorAll('.event-card:not(.is-dragging)'));

        return draggableElements.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            const offsetX = clientX - box.left - box.width / 2;

            if (offsetX < 0 && offsetX > closest.offsetX) {
                return { offsetX, element: child };
            }

            return closest;
        }, { offsetX: Number.NEGATIVE_INFINITY, element: null }).element;
    };

    const getRankedCards = () => {
        return bucketZones
            .slice()
            .sort((left, right) => Number(right.dataset.star) - Number(left.dataset.star))
            .flatMap((zone) => Array.from(zone.querySelectorAll('.event-card')).map((card) => ({
                card,
                star: Number(zone.dataset.star),
            })));
    };

    const renderResults = () => {
        updateAllCardStars();
        const rankedCards = getRankedCards();
        const placed = rankedCards.length;
        const remaining = initialOrder.length - placed;

        if (placedCount) placedCount.textContent = String(placed);

        if (statusText) {
            if (finalized) {
                statusText.textContent = `Finalisiert: ${placed} Events sind fest im Gesamtranking.`;
            } else if (remaining === 0) {
                statusText.textContent = 'Alle Events sind zugewiesen. Du kannst jetzt das Ergebnis finalisieren.';
            } else {
                statusText.textContent = `${remaining} Events warten noch auf eine Sterne-Kategorie.`;
            }
        }

        if (resultBody) {
            resultBody.innerHTML = rankedCards.map((entry, index) => {
            const eventName = escapeHtml(entry.card.dataset.eventName || 'Unbenanntes Event');
            const eventLocation = escapeHtml(entry.card.dataset.eventLocation || 'Unbekannter Ort');

            return `
                <tr>
                    <td>${index + 1}</td>
                    <td>${eventName}</td>
                    <td>${'★'.repeat(entry.star)}</td>
                    <td>${eventLocation}</td>
                </tr>
            `;
        }).join('');
        }
    };

    const setCardDraggability = (enabled) => {
        board.querySelectorAll('.event-card').forEach((card) => {
            card.draggable = enabled;
        });
    };

    const resetBoard = () => {
        finalized = false;
        document.body.classList.remove('is-finalized');
        setCardDraggability(true);

        initialOrder.forEach((eventId) => {
            const card = cardsById.get(eventId);
            if (card) {
                card.dataset.star = '';
                pool.appendChild(card);
            }
        });

        renderResults();
    };

    const finalizeBoard = async () => {
        const rankedCards = getRankedCards();

        if (rankedCards.length !== initialOrder.length) {
            const remaining = initialOrder.length - rankedCards.length;
            if (statusText) statusText.textContent = `Bitte weise zuerst noch ${remaining} Events einer Sterne-Kategorie zu.`;
            return;
        }

        finalized = true;
        document.body.classList.add('is-finalized');
        setCardDraggability(false);
        if (finalizeButton) {
            finalizeButton.disabled = true;
        }
        renderResults();
        if (statusText) statusText.textContent = 'Abgeschlossen. Weiter zur nächsten Persona...';

        try {
            const response = await fetch(completeUrl, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'fetch',
                },
            });
            const payload = await response.json();

            window.setTimeout(() => {
                window.location.assign(payload.nextUrl || completeUrl);
            }, 500);
        } catch (error) {
            finalized = false;
            document.body.classList.remove('is-finalized');
            setCardDraggability(true);
            if (finalizeButton) {
                finalizeButton.disabled = false;
            }
            if (statusText) statusText.textContent = 'Der Abschluss konnte nicht bestätigt werden. Bitte versuche es erneut.';
        }
    };

    const downloadResult = () => {
        const rankedCards = getRankedCards();

        if (!finalized || rankedCards.length !== initialOrder.length) {
            if (statusText) statusText.textContent = 'Bitte das Ranking zuerst finalisieren, bevor du exportierst.';
            return;
        }

        const payload = {
            persona: {
                id: document.querySelector('.page-shell') ? document.querySelector('.page-shell').dataset.personaId : '',
                name: document.querySelector('.page-shell') ? document.querySelector('.page-shell').dataset.personaName : '',
                bio: board.querySelector('.persona-bio') ? board.querySelector('.persona-bio').textContent : '',
            },
            generatedAt: new Date().toISOString(),
            ranking: rankedCards.map((entry, index) => ({
                position: index + 1,
                eventId: entry.card.dataset.eventId,
                eventName: entry.card.dataset.eventName,
                starCategory: entry.star,
                location: entry.card.dataset.eventLocation,
                tags: (entry.card.dataset.eventTags || '').split(', ').filter(Boolean),
            })),
        };

        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');

        link.href = url;
        link.download = 'evaluation-ranking.json';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    board.querySelectorAll('.event-card').forEach((card) => {
        const openDetailsButton = card.querySelector('[data-event-action="open-details"]');

        if (openDetailsButton) {
            openDetailsButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                openEventDetails(card);
            });
        }

        card.addEventListener('dragstart', (event) => {
            if (event.target instanceof Element && event.target.closest('[data-event-action="open-details"]')) {
                event.preventDefault();
                return;
            }

            if (finalized) {
                event.preventDefault();
                return;
            }

            closeEventDetails();

            draggedCard = card;
            card.classList.add('is-dragging');
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', card.dataset.eventId || '');
        });

        card.addEventListener('dragend', () => {
            card.classList.remove('is-dragging');
            draggedCard = null;
            allDropzones.forEach((zone) => zone.classList.remove('is-over'));
            renderResults();
        });
    });

    allDropzones.forEach((zone) => {
        zone.addEventListener('dragover', (event) => {
            if (finalized) {
                return;
            }

            event.preventDefault();

            if (!draggedCard) {
                return;
            }

            const afterElement = getDragAfterElement(zone, event.clientX);

            if (afterElement == null) {
                zone.appendChild(draggedCard);
            } else {
                zone.insertBefore(draggedCard, afterElement);
            }

            updateCardStar(draggedCard);
            zone.classList.add('is-over');
            renderResults();
        });

        zone.addEventListener('dragleave', () => {
            zone.classList.remove('is-over');
        });

        zone.addEventListener('drop', (event) => {
            if (finalized) {
                return;
            }

            event.preventDefault();
            zone.classList.remove('is-over');

            if (draggedCard) {
                updateCardStar(draggedCard);
                renderResults();
            }
        });
    });

    if (resetButton) {
        resetButton.addEventListener('click', resetBoard);
    }

    if (finalizeButton) {
        finalizeButton.addEventListener('click', finalizeBoard);
    }

    if (downloadButton) {
        downloadButton.addEventListener('click', downloadResult);
    }

    modalCloseButtons.forEach((button) => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            closeEventDetails();
        });
    });

    if (modal) {
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeEventDetails();
            }
        });
    }

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') {
            return;
        }

        if (modal && !modal.hidden) {
            closeEventDetails();
        }
    });

    renderResults();
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeRankingApp);
} else {
    initializeRankingApp();
}

function initializeRankingApp() {
    document.querySelectorAll('[data-persona-board]').forEach(initializeRankingBoard);
}
