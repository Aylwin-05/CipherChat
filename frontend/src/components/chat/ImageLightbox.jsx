import { useEffect } from "react";

export default function ImageLightbox({
    attachment,
    url,
    onClose,
}) {

    useEffect(() => {

        function handleKeyDown(event) {

            if (event.key === "Escape") {

                onClose();

            }

        }

        window.addEventListener(
            "keydown",
            handleKeyDown,
        );

        return () =>
            window.removeEventListener(
                "keydown",
                handleKeyDown,
            );

    }, [onClose]);

    if (!attachment || !url) return null;

    return (

        <div
            className="lightbox-overlay"
            onClick={onClose}
        >

            <div
                className="lightbox-header"
                onClick={event =>
                    event.stopPropagation()
                }
            >

                <span className="lightbox-name">

                    {attachment.original_name || "Image"}

                </span>

                <button
                    type="button"
                    className="lightbox-close"
                    onClick={onClose}
                    aria-label="Close"
                >

                    ✕

                </button>

            </div>

            <img
                className="lightbox-image"
                src={url}
                alt={attachment.original_name || "Image"}
                onClick={event =>
                    event.stopPropagation()
                }
            />

            <div
                className="lightbox-footer"
                onClick={event =>
                    event.stopPropagation()
                }
            >

                <a
                    className="lightbox-download"
                    href={url}
                    download={attachment.original_name || "image"}
                >

                    ⬇ Download

                </a>

            </div>

        </div>

    );

}