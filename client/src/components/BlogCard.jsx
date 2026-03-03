import { Link } from 'react-router-dom';
import { FiHeart, FiMessageCircle, FiBookmark } from 'react-icons/fi';

export default function BlogCard({ blog }) {
    const excerpt = blog.content.length > 150
        ? blog.content.substring(0, 150).replace(/[#*_`\[\]]/g, '') + '...'
        : blog.content.replace(/[#*_`\[\]]/g, '');

    return (
        <article className="blog-card">
            {blog.coverImage && (
                <Link to={`/blogs/${blog._id}`}>
                    <img src={blog.coverImage} alt={blog.title} className="blog-card-cover" />
                </Link>
            )}
            <div className="blog-card-body">
                <div className="blog-card-meta">
                    <Link to={`/profile/${blog.author?._id}`} className="blog-card-author">
                        {blog.author?.profilePicUrl ? (
                            <img src={blog.author.profilePicUrl} alt="" className="author-avatar" />
                        ) : (
                            <div className="author-avatar-placeholder">
                                {blog.author?.name?.charAt(0) || '?'}
                            </div>
                        )}
                        <span>{blog.author?.name}</span>
                    </Link>
                    <time className="blog-card-date">
                        {new Date(blog.createdAt).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                        })}
                    </time>
                </div>

                <Link to={`/blogs/${blog._id}`} className="blog-card-title-link">
                    <h2 className="blog-card-title">{blog.title}</h2>
                </Link>

                <p className="blog-card-excerpt">{excerpt}</p>

                {blog.tags?.length > 0 && (
                    <div className="blog-card-tags">
                        {blog.tags.map((tag) => (
                            <span key={tag} className="tag">#{tag}</span>
                        ))}
                    </div>
                )}

                <div className="blog-card-stats">
                    <span className="stat">
                        <FiHeart /> {blog.likes?.length || 0}
                    </span>
                    <span className="stat">
                        <FiMessageCircle /> {blog.comments?.length || 0}
                    </span>
                    <span className="stat">
                        <FiBookmark /> {blog.bookmarks?.length || 0}
                    </span>
                </div>
            </div>
        </article>
    );
}
