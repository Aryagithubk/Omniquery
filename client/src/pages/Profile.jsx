import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { FiCamera, FiEdit2, FiSave, FiX } from 'react-icons/fi';
import { useAuth } from '../context/AuthContext';
import BlogCard from '../components/BlogCard';
import API from '../api/axios';

export default function Profile() {
    const { id } = useParams();
    const { user: currentUser, updateUser } = useAuth();
    const fileInputRef = useRef(null);

    const [profileUser, setProfileUser] = useState(null);
    const [blogs, setBlogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editing, setEditing] = useState(false);
    const [editData, setEditData] = useState({ name: '', bio: '' });
    const [uploading, setUploading] = useState(false);

    const userId = id || currentUser?._id;
    const isOwnProfile = !id || id === currentUser?._id;

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                if (isOwnProfile && currentUser) {
                    setProfileUser(currentUser);
                    setEditData({ name: currentUser.name, bio: currentUser.bio || '' });
                } else if (userId) {
                    // For other users, we fetch their blogs and get author info from there
                    const res = await API.get('/blogs', { params: { author: userId } });
                    if (res.data.length > 0) {
                        setProfileUser(res.data[0].author);
                    }
                }

                const res = await API.get('/blogs', { params: { author: userId } });
                setBlogs(res.data);
            } catch (err) {
                console.error(err);
            } finally {
                setLoading(false);
            }
        };

        if (userId) fetchData();
    }, [userId, currentUser, isOwnProfile]);

    const handleProfilePicUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploading(true);
        try {
            const formData = new FormData();
            formData.append('image', file);
            const uploadRes = await API.post('/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });

            const res = await API.put('/auth/profile', {
                profilePicUrl: uploadRes.data.url,
            });
            setProfileUser(res.data);
            updateUser(res.data);
        } catch (err) {
            console.error(err);
        } finally {
            setUploading(false);
        }
    };

    const handleSaveProfile = async () => {
        try {
            const res = await API.put('/auth/profile', editData);
            setProfileUser(res.data);
            updateUser(res.data);
            setEditing(false);
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

    return (
        <div className="profile-page">
            <div className="profile-header">
                <div className="profile-avatar-section">
                    <div className="profile-avatar-wrapper">
                        {profileUser?.profilePicUrl ? (
                            <img src={profileUser.profilePicUrl} alt="" className="profile-avatar" />
                        ) : (
                            <div className="profile-avatar-placeholder">
                                {profileUser?.name?.charAt(0) || '?'}
                            </div>
                        )}
                        {isOwnProfile && (
                            <button
                                className="avatar-upload-btn"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={uploading}
                            >
                                <FiCamera />
                            </button>
                        )}
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleProfilePicUpload}
                            accept="image/*"
                            hidden
                        />
                    </div>
                </div>

                <div className="profile-info">
                    {editing ? (
                        <div className="profile-edit-form">
                            <input
                                type="text"
                                value={editData.name}
                                onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                                className="profile-edit-input"
                                placeholder="Name"
                            />
                            <textarea
                                value={editData.bio}
                                onChange={(e) => setEditData({ ...editData, bio: e.target.value })}
                                className="profile-edit-textarea"
                                placeholder="Write a short bio..."
                                maxLength={300}
                            />
                            <div className="profile-edit-actions">
                                <button onClick={handleSaveProfile} className="btn btn-primary btn-sm">
                                    <FiSave /> Save
                                </button>
                                <button onClick={() => setEditing(false)} className="btn btn-ghost btn-sm">
                                    <FiX /> Cancel
                                </button>
                            </div>
                        </div>
                    ) : (
                        <>
                            <h1 className="profile-name">{profileUser?.name}</h1>
                            <p className="profile-username">@{profileUser?.username}</p>
                            {profileUser?.bio && <p className="profile-bio">{profileUser.bio}</p>}
                            {isOwnProfile && (
                                <button onClick={() => setEditing(true)} className="btn btn-ghost btn-sm">
                                    <FiEdit2 /> Edit Profile
                                </button>
                            )}
                        </>
                    )}
                </div>

                <div className="profile-stats">
                    <div className="stat-item">
                        <span className="stat-value">{blogs.length}</span>
                        <span className="stat-label">Posts</span>
                    </div>
                </div>
            </div>

            <section className="profile-blogs">
                <h2 className="section-title">
                    {isOwnProfile ? 'Your Posts' : `Posts by ${profileUser?.name}`}
                </h2>

                {blogs.length > 0 ? (
                    <div className="blog-grid">
                        {blogs.map((blog) => (
                            <BlogCard key={blog._id} blog={blog} />
                        ))}
                    </div>
                ) : (
                    <div className="empty-state">
                        <p>No posts yet</p>
                    </div>
                )}
            </section>
        </div>
    );
}
