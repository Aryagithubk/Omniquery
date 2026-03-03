import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FiHeart, FiBookmark, FiEdit, FiTrash2, FiArrowLeft } from 'react-icons/fi';
import { useAuth } from '../context/AuthContext';
import CommentSection from '../components/CommentSection';
import API from '../api/axios';

export default function BlogDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const [blog, setBlog] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchBlog = async () => {
            try {
                const res = await API.get(`/blogs/${id}`);
                setBlog(res.data);
            } catch (err) {
                console.error(err);
                navigate('/');
            } finally {
                setLoading(false);
            }
        };
        fetchBlog();
    }, [id, navigate]);

    const handleLike = async () => {
        if (!user) return navigate('/login');
        try {
            const res = await API.put(`/blogs/${id}/like`);
            setBlog({ ...blog, likes: res.data.likes });
        } catch (err) {
            console.error(err);
        }
    };

    const handleBookmark = async () => {
        if (!user) return navigate('/login');
        try {
            const res = await API.put(`/blogs/${id}/bookmark`);
            setBlog({ ...blog, bookmarks: res.data.bookmarks });
        } catch (err) {
            console.error(err);
        }
    };

    const handleDelete = async () => {
        if (!window.confirm('Are you sure you want to delete this post?')) return;
        try {
            await API.delete(`/blogs/${id}`);
            navigate('/');
        } catch (err) {
            console.error(err);
        }
    };

    if (loading) {
        return (
            <div className="loading-screen">
                <div className="spinner"></div>
            </div>
        );
    }

    if (!blog) return null;

    const isAuthor = user && user._id === blog.author?._id;
    const isLiked = user && blog.likes?.includes(user._id);
    const isBookmarked = user && blog.bookmarks?.includes(user._id);

    return (
        <div className="blog-detail-page">
            <button onClick={() => navigate(-1)} className="back-btn">
                <FiArrowLeft /> Back
            </button>

            <article className="blog-detail">
                {blog.coverImage && (
                    <img src={blog.coverImage} alt={blog.title} className="blog-detail-cover" />
                )}

                <header className="blog-detail-header">
                    <h1 className="blog-detail-title">{blog.title}</h1>

                    <div className="blog-detail-meta">
                        <Link to={`/profile/${blog.author?._id}`} className="blog-detail-author">
                            {blog.author?.profilePicUrl ? (
                                <img src={blog.author.profilePicUrl} alt="" className="author-avatar" />
                            ) : (
                                <div className="author-avatar-placeholder">
                                    {blog.author?.name?.charAt(0) || '?'}
                                </div>
                            )}
                            <div>
                                <span className="author-name">{blog.author?.name}</span>
                                <time className="blog-detail-date">
                                    {new Date(blog.createdAt).toLocaleDateString('en-US', {
                                        month: 'long',
                                        day: 'numeric',
                                        year: 'numeric',
                                    })}
                                </time>
                            </div>
                        </Link>

                        {isAuthor && (
                            <div className="blog-detail-actions">
                                <Link to={`/edit/${blog._id}`} className="btn btn-ghost">
                                    <FiEdit /> Edit
                                </Link>
                                <button onClick={handleDelete} className="btn btn-ghost btn-danger">
                                    <FiTrash2 /> Delete
                                </button>
                            </div>
                        )}
                    </div>

                    {blog.tags?.length > 0 && (
                        <div className="blog-detail-tags">
                            {blog.tags.map((tag) => (
                                <span key={tag} className="tag">#{tag}</span>
                            ))}
                        </div>
                    )}
                </header>

                <div className="blog-detail-content markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{blog.content}</ReactMarkdown>
                </div>

                <div className="blog-detail-engagement">
                    <button
                        onClick={handleLike}
                        className={`engagement-btn ${isLiked ? 'active liked' : ''}`}
                    >
                        <FiHeart className={isLiked ? 'filled' : ''} />
                        <span>{blog.likes?.length || 0}</span>
                    </button>

                    <button
                        onClick={handleBookmark}
                        className={`engagement-btn ${isBookmarked ? 'active bookmarked' : ''}`}
                    >
                        <FiBookmark className={isBookmarked ? 'filled' : ''} />
                        <span>{isBookmarked ? 'Saved' : 'Save'}</span>
                    </button>
                </div>

                <CommentSection
                    blogId={blog._id}
                    comments={blog.comments || []}
                    onCommentsUpdate={(updatedComments) =>
                        setBlog({ ...blog, comments: updatedComments })
                    }
                />
            </article>
        </div>
    );
}
