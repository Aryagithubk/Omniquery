import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { FiSend, FiTrash2 } from 'react-icons/fi';
import API from '../api/axios';

export default function CommentSection({ blogId, comments, onCommentsUpdate }) {
    const { user } = useAuth();
    const [text, setText] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!text.trim()) return;

        setLoading(true);
        try {
            const res = await API.post(`/blogs/${blogId}/comment`, { text });
            onCommentsUpdate(res.data);
            setText('');
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (commentId) => {
        try {
            await API.delete(`/blogs/${blogId}/comment/${commentId}`);
            onCommentsUpdate(comments.filter((c) => c._id !== commentId));
        } catch (err) {
            console.error(err);
        }
    };

    return (
        <div className="comment-section">
            <h3 className="comment-title">Comments ({comments.length})</h3>

            {user && (
                <form onSubmit={handleSubmit} className="comment-form">
                    <div className="comment-input-row">
                        {user.profilePicUrl ? (
                            <img src={user.profilePicUrl} alt="" className="comment-avatar" />
                        ) : (
                            <div className="comment-avatar-placeholder">
                                {user.name?.charAt(0)}
                            </div>
                        )}
                        <input
                            type="text"
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            placeholder="Write a comment..."
                            className="comment-input"
                        />
                        <button type="submit" className="comment-submit" disabled={loading || !text.trim()}>
                            <FiSend />
                        </button>
                    </div>
                </form>
            )}

            <div className="comment-list">
                {comments.map((comment) => (
                    <div key={comment._id} className="comment-item">
                        <div className="comment-header">
                            {comment.user?.profilePicUrl ? (
                                <img src={comment.user.profilePicUrl} alt="" className="comment-avatar" />
                            ) : (
                                <div className="comment-avatar-placeholder">
                                    {comment.user?.name?.charAt(0) || '?'}
                                </div>
                            )}
                            <div className="comment-info">
                                <span className="comment-author">{comment.user?.name}</span>
                                <time className="comment-date">
                                    {new Date(comment.createdAt).toLocaleDateString('en-US', {
                                        month: 'short',
                                        day: 'numeric',
                                    })}
                                </time>
                            </div>
                            {user && (user._id === comment.user?._id) && (
                                <button
                                    onClick={() => handleDelete(comment._id)}
                                    className="comment-delete"
                                >
                                    <FiTrash2 />
                                </button>
                            )}
                        </div>
                        <p className="comment-text">{comment.text}</p>
                    </div>
                ))}

                {comments.length === 0 && (
                    <p className="no-comments">No comments yet. Be the first to share your thoughts!</p>
                )}
            </div>
        </div>
    );
}
