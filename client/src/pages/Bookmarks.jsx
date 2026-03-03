import { useState, useEffect } from 'react';
import { FiBookmark } from 'react-icons/fi';
import BlogCard from '../components/BlogCard';
import API from '../api/axios';

export default function Bookmarks() {
    const [blogs, setBlogs] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchBookmarks = async () => {
            try {
                const res = await API.get('/blogs/bookmarked');
                setBlogs(res.data);
            } catch (err) {
                console.error(err);
            } finally {
                setLoading(false);
            }
        };
        fetchBookmarks();
    }, []);

    if (loading) {
        return (
            <div className="loading-screen">
                <div className="spinner"></div>
            </div>
        );
    }

    return (
        <div className="bookmarks-page">
            <h1 className="page-title">
                <FiBookmark /> Your Bookmarks
            </h1>

            {blogs.length > 0 ? (
                <div className="blog-grid">
                    {blogs.map((blog) => (
                        <BlogCard key={blog._id} blog={blog} />
                    ))}
                </div>
            ) : (
                <div className="empty-state">
                    <FiBookmark className="empty-icon" />
                    <h3>No bookmarks yet</h3>
                    <p>Save articles to read later</p>
                </div>
            )}
        </div>
    );
}
