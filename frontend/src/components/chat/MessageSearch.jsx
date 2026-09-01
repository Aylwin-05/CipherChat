import { useState, useCallback } from "react";
import api from "../../api/api";
import "./MessageSearch.css";

export default function MessageSearch({ conversationId, onSelect }) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searched, setSearched] = useState(false);

    const handleSearch = useCallback(async () => {
        if (!query.trim() || !conversationId) return;

        setLoading(true);
        setSearched(true);
        try {
            const { data } = await api.get(
                `/messages/search/${conversationId}`,
                { params: { q: query.trim(), limit: 50 } }
            );
            setResults(data.results || []);
        } catch {
            setResults([]);
        } finally {
            setLoading(false);
        }
    }, [query, conversationId]);

    const handleSubmit = (e) => {
        e.preventDefault();
        handleSearch();
    };

    return (
        <div className="message-search">
            <form className="message-search__form" onSubmit={handleSubmit}>
                <input
                    className="message-search__input"
                    type="text"
                    placeholder="Search messages…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    autoFocus
                />
                <button
                    type="submit"
                    className="message-search__btn"
                    disabled={!query.trim() || loading}
                >
                    {loading ? "…" : "Search"}
                </button>
            </form>

            {searched && (
                <div className="message-search__results">
                    {results.length === 0 ? (
                        <p className="message-search__empty">
                            No messages found.
                        </p>
                    ) : (
                        <ul className="message-search__list">
                            {results.map((msg) => (
                                <li
                                    key={msg.id}
                                    className="message-search__item"
                                    onClick={() => onSelect?.(msg)}
                                >
                                    <span className="message-search__snippet">
                                        {msg.ciphertext?.slice(0, 120) || "…"}
                                    </span>
                                    <span className="message-search__time">
                                        {msg.created_at
                                            ? new Date(msg.created_at).toLocaleString()
                                            : ""}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
