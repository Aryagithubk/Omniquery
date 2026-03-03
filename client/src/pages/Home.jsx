import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { FiSearch, FiPenTool } from 'react-icons/fi';
import { useAuth } from '../context/AuthContext';
import BlogCard from '../components/BlogCard';
import API from '../api/axios';

export default function Home() {
    const { user } = useAuth();
    const [blogs, setBlogs] = useState([]);
    const [search, setSearch] = useState('');
    const [loading, setLoading] = useState(true);

    const fetchBlogs = async (query = '') => {
        setLoading(true);
        try {
            const res = await API.get('/blogs', { params: { search: query } });
            setBlogs(res.data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchBlogs();
    }, []);

    const handleSearch = (e) => {
        e.preventDefault();
        fetchBlogs(search);
    };

    return (
        <div className="home-page">
            <section className="hero">
                <div className="hero-content">
                    <h1 className="hero-title">
                        Discover stories,
                        <br />
                        <span className="gradient-text">ideas & knowledge</span>
                    </h1>
                    <p className="hero-subtitle">
                        A place to read, write, and deepen your understanding
                    </p>

                    <form className="search-bar" onSubmit={handleSearch}>
                        <FiSearch className="search-icon" />
                        <input
                            type="text"
                            placeholder="Search articles..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            id="search-input"
                        />
                        <button type="submit" className="btn btn-primary">Search</button>
                    </form>

                    {user && (
                        <Link to="/create" className="btn btn-accent hero-cta">
                            <FiPenTool /> Start Writing
                        </Link>
                    )}
                </div>
            </section>

            <section className="blog-feed">
                <h2 className="section-title">Latest Posts</h2>

                {loading ? (
                    <div className="loading-grid">
                        {[1, 2, 3].map((i) => (
                            <div key={i} className="skeleton-card">
                                <div className="skeleton skeleton-cover"></div>
                                <div className="skeleton skeleton-line"></div>
                                <div className="skeleton skeleton-line short"></div>
                            </div>
                        ))}
                    </div>
                ) : blogs.length > 0 ? (
                    <div className="blog-grid">
                        {blogs.map((blog) => (
                            <BlogCard key={blog._id} blog={blog} />
                        ))}
                    </div>
                ) : (
                    <div className="empty-state">
                        <FiPenTool className="empty-icon" />
                        <h3>No posts yet</h3>
                        <p>Be the first to share your story!</p>
                        {user && (
                            <Link to="/create" className="btn btn-primary">Write a Post</Link>
                        )}
                    </div>
                )}
            </section>
        </div>
    );
}
