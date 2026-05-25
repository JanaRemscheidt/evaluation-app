const initializeRankingBoard = (board) => {
    const pool = board.querySelector('[data-dropzone="pool"]');
    const bucketZones = Array.from(board.querySelectorAll('[data-dropzone="bucket"]'));
    const resetButton = board.querySelector('[data-action="reset"]');
    const downloadButton = board.querySelector('[data-action="download"]');
    const resultBody = board.querySelector('.ranking-result-body');
    const statusText = board.querySelector('.ranking-status');
    const placedCount = board.querySelector('.placed-count');
    const pageShell = board.closest('.page-shell');
    const finalizeButton = pageShell ? pageShell.querySelector('[data-action="finalize"]') : null;
    const siteFooter = pageShell ? pageShell.querySelector('.site-footer') : null;
    const footerMessage = siteFooter ? siteFooter.querySelector('p') : null;
    const completeUrl = pageShell ? pageShell.dataset.completeUrl : '';
    const participantInput = pageShell ? pageShell.querySelector('[name="participantLabel"]') : null;
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
    let participantSaveTimer = null;
    const finalizeLabel = finalizeButton ? finalizeButton.textContent.trim() : 'Weiter';
    const fallbackFinalLabel = 'Fertig';

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

    const updateBucketLayoutState = () => {
        const bucketCounts = bucketZones.map((zone) => {
            const bucket = zone.closest('.bucket');
            const cardCount = zone.querySelectorAll('.event-card').length;
            const bucketGrow = cardCount > 2 ? (3.2 + ((cardCount - 3) * 0.9)) : 0.7;

            if (bucket) {
                bucket.dataset.cardCount = String(cardCount);
                bucket.classList.toggle('is-expanded', cardCount > 2);
                bucket.style.setProperty('--bucket-grow', String(bucketGrow));
            }

            return cardCount;
        });

        const hasExpandedBucket = bucketCounts.some((count) => count > 2);

        board.classList.toggle('has-dense-buckets', hasExpandedBucket);

        bucketZones.forEach((zone) => {
            const bucket = zone.closest('.bucket');
            const cardCount = Number(bucket ? bucket.dataset.cardCount || '0' : '0');

            if (bucket) {
                bucket.classList.toggle('is-compact', hasExpandedBucket && cardCount <= 2);

                if (hasExpandedBucket && cardCount <= 2) {
                    bucket.style.setProperty('--bucket-grow', '0.55');
                } else if (cardCount > 2) {
                    bucket.style.setProperty('--bucket-grow', String(3.2 + ((cardCount - 3) * 0.9)));
                } else {
                    bucket.style.setProperty('--bucket-grow', '0.7');
                }
            }
        });
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

    const buildSubmissionPayload = () => {
        const rankedCards = getRankedCards();
        const participantLabel = participantInput ? participantInput.value.trim() : (pageShell ? pageShell.dataset.participantLabel || '' : '');

        return {
            persona: {
                id: document.querySelector('.page-shell') ? document.querySelector('.page-shell').dataset.personaId : '',
                name: document.querySelector('.page-shell') ? document.querySelector('.page-shell').dataset.personaName : '',
                bio: board.querySelector('.persona-bio') ? board.querySelector('.persona-bio').textContent : '',
            },
            participantLabel,
            generatedAt: new Date().toISOString(),
            ranking: rankedCards.map((entry, index) => ({
                position: index + 1,
                eventId: entry.card.dataset.eventId,
                eventName: entry.card.dataset.eventName,
                eventType: entry.card.dataset.eventType,
                starCategory: entry.star,
                location: entry.card.dataset.eventLocation,
                tags: (entry.card.dataset.eventTags || '').split(', ').filter(Boolean),
            })),
        };
    };

    const renderResults = () => {
        updateAllCardStars();
        updateBucketLayoutState();
        const rankedCards = getRankedCards();
        const placed = rankedCards.length;
        const remaining = initialOrder.length - placed;
        const personaIndex = Number(pageShell ? pageShell.dataset.personaIndex || 0 : 0);
        const personaCount = Number(pageShell ? pageShell.dataset.personaCount || 0 : 0);
        const nextPersonaIndex = personaIndex + 1;
        const isLastPersona = personaIndex > 0 && personaCount > 0 && personaIndex === personaCount;

        if (placedCount) placedCount.textContent = String(placed);

        if (footerMessage) {
            footerMessage.hidden = remaining !== 0;
            if (isLastPersona) {
                footerMessage.textContent = 'Wenn du bereit bist, kannst du die letzte Persona abschließen.';
            } else if (nextPersonaIndex > 0 && personaCount > 0 && nextPersonaIndex <= personaCount) {
                footerMessage.textContent = `Wenn du bereit bist, geht es mit Persona ${nextPersonaIndex} (von ${personaCount}) weiter.`;
            } else {
                footerMessage.textContent = 'Wenn du bereit bist, geht es mit der nächsten Persona weiter.';
            }
        }

        if (statusText) {
            if (finalized) {
                statusText.textContent = `Finalisiert: ${placed} Events sind fest im Gesamtranking.`;
            } else if (remaining === 0) {
                statusText.textContent = 'Alle Events sind zugewiesen. Du kannst jetzt das Ergebnis finalisieren.';
            } else {
                statusText.textContent = `${remaining} Events warten noch auf eine Sterne-Kategorie.`;
            }
        }

        if (finalizeButton) {
            const ready = !finalized && remaining === 0;
            finalizeButton.disabled = !ready;
            finalizeButton.setAttribute('aria-disabled', String(!ready));
            finalizeButton.classList.toggle('is-ready', ready);

            if (!finalizeButton.classList.contains('is-loading')) {
                finalizeButton.textContent = isLastPersona ? fallbackFinalLabel : finalizeLabel;
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

        if (finalizeButton) {
            finalizeButton.classList.remove('is-loading');
            finalizeButton.textContent = finalizeLabel;
        }

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
        const payload = buildSubmissionPayload();
        const rankedCards = payload.ranking;
        const participantLabel = payload.participantLabel || '';

        if (rankedCards.length !== initialOrder.length) {
            const remaining = initialOrder.length - rankedCards.length;
            if (statusText) statusText.textContent = `Bitte weise zuerst noch ${remaining} Events einer Sterne-Kategorie zu.`;
            return;
        }

        if (!participantLabel) {
            if (statusText) statusText.textContent = 'Bitte gib zuerst deinen Namen oder ein Kürzel an.';
            if (participantInput) participantInput.focus();
            return;
        }

        finalized = true;
        document.body.classList.add('is-finalized');
        setCardDraggability(false);
        if (finalizeButton) {
            finalizeButton.classList.add('is-loading');
            finalizeButton.textContent = 'Lädt...';
            finalizeButton.disabled = true;
            finalizeButton.setAttribute('aria-disabled', 'true');
        }
        renderResults();
        if (statusText) statusText.textContent = 'Abgeschlossen. Weiter zur nächsten Persona...';

        try {
            const response = await fetch(completeUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'fetch',
                },
                body: JSON.stringify(payload),
            });

            const responsePayload = await response.json();

            if (!response.ok) {
                throw new Error(responsePayload.error || 'Ranking konnte nicht gespeichert werden.');
            }

            window.setTimeout(() => {
                window.location.assign(responsePayload.nextUrl || completeUrl);
            }, 500);
        } catch (error) {
            finalized = false;
            document.body.classList.remove('is-finalized');
            setCardDraggability(true);
            if (finalizeButton) {
                finalizeButton.classList.remove('is-loading');
                finalizeButton.disabled = false;
                finalizeButton.textContent = finalizeLabel;
            }
            if (statusText) statusText.textContent = 'Der Abschluss konnte nicht bestätigt werden. Bitte versuche es erneut.';
        }
    };

    const downloadResult = () => {
        const payload = buildSubmissionPayload();
        const rankedCards = payload.ranking;

        if (!finalized || rankedCards.length !== initialOrder.length) {
            if (statusText) statusText.textContent = 'Bitte das Ranking zuerst finalisieren, bevor du exportierst.';
            return;
        }

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

    const persistParticipantLabel = async () => {
        if (!participantInput) {
            return;
        }

        const participantLabel = participantInput.value.trim();

        if (!participantLabel) {
            return;
        }

        if (pageShell) {
            pageShell.dataset.participantLabel = participantLabel;
        }

        try {
            await fetch('/participant-label', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'fetch',
                },
                body: JSON.stringify({ participantLabel }),
            });
        } catch {
            // Best effort only; the label is also included in the final submission.
        }
    };

    if (participantInput) {
        participantInput.addEventListener('input', () => {
            window.clearTimeout(participantSaveTimer);
            participantSaveTimer = window.setTimeout(() => {
                persistParticipantLabel();
            }, 300);
        });

        participantInput.addEventListener('blur', () => {
            window.clearTimeout(participantSaveTimer);
            persistParticipantLabel();
        });
    }

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
    // Render persona counter (e.g. "Persona 3/6") if present in the page shell.
    document.querySelectorAll('.page-shell').forEach((shell) => {
        const counter = shell.querySelector('.persona-counter');
        const footerMessage = shell.querySelector('.site-footer p');
        if (!counter) return;

        const idx = Number(shell.dataset.personaIndex || 0);
        const total = Number(shell.dataset.personaCount || 0);

        if (idx > 0 && total > 0) {
            counter.textContent = `Persona ${idx}/${total}`;
        } else {
            counter.textContent = '';
        }

        if (footerMessage && idx > 0 && total > 0) {
            const nextIdx = idx + 1;

            if (idx === total) {
                footerMessage.textContent = 'Wenn du bereit bist, kannst du die letzte Persona abschließen.';
            } else if (nextIdx <= total) {
                footerMessage.textContent = `Wenn du bereit bist, geht es mit Persona ${nextIdx} (von ${total}) weiter.`;
            }
        }
    });

    document.querySelectorAll('[data-persona-board]').forEach(initializeRankingBoard);
}
