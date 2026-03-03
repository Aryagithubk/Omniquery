import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import MdEditor from 'react-markdown-editor-lite';
import MarkdownIt from 'markdown-it';
import 'react-markdown-editor-lite/lib/index.css';
import { FiImage, FiSend, FiX } from 'react-icons/fi';
import API from '../api/axios';

const mdParser = new MarkdownIt();

export default function CreateBlog() {
    const navigate = useNavigate();
    const fileInputRef = useRef(null);
    const [title, setTitle] = useState('');
    const [content, setContent] = useState('');
    const [coverImage, setCoverImage] = useState('');
    const [tags, setTags] = useState('');
    const [uploading, setUploading] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleImageUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploading(true);
        try {
            const formData = new FormData();
            formData.append('image', file);
            const res = await API.post('/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            setCoverImage(res.data.url);
        } catch (err) {
            setError('Image upload failed');
        } finally {
            setUploading(false);
        }
    };

    // Handle image upload inside markdown editor
    const handleEditorImageUpload = async (file) => {
        try {
            const formData = new FormData();
            formData.append('image', file);
            const res = await API.post('/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return res.data.url;
        } catch (err) {
            console.error('Editor image upload failed', err);
            return '';
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (!title.trim() || !content.trim()) {
            return setError('Title and content are required');
        }

        setLoading(true);
        try {
            const blogData = {
                title,
                content,
                coverImage,
                tags: tags
                    .split(',')
                    .map((t) => t.trim().toLowerCase())
                    .filter(Boolean),
            };
            const res = await API.post('/blogs', blogData);
            navigate(`/blogs/${res.data._id}`);
        } catch (err) {
            setError(err.response?.data?.message || 'Failed to create blog');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="editor-page">
            <div className="editor-container">
                <h1 className="editor-title">Create New Post</h1>

                {error && <div className="alert alert-error">{error}</div>}

                <form onSubmit={handleSubmit}>
                    {/* Cover Image */}
                    <div className="cover-upload">
                        {coverImage ? (
                            <div className="cover-preview">
                                <img src={coverImage} alt="Cover" />
                                <button
                                    type="button"
                                    className="cover-remove"
                                    onClick={() => setCoverImage('')}
                                >
                                    <FiX />
                                </button>
                            </div>
                        ) : (
                            <button
                                type="button"
                                className="cover-upload-btn"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={uploading}
                            >
                                <FiImage />
                                {uploading ? 'Uploading...' : 'Add Cover Image'}
                            </button>
                        )}
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleImageUpload}
                            accept="image/*"
                            hidden
                        />
                    </div>

                    {/* Title */}
                    <input
                        type="text"
                        className="editor-title-input"
                        placeholder="Post title..."
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        id="blog-title"
                    />

                    {/* Tags */}
                    <input
                        type="text"
                        className="editor-tags-input"
                        placeholder="Tags (comma separated, e.g. javascript, react, webdev)"
                        value={tags}
                        onChange={(e) => setTags(e.target.value)}
                        id="blog-tags"
                    />

                    {/* Markdown Editor */}
                    <div className="markdown-editor-wrapper">
                        <MdEditor
                            value={content}
                            style={{ height: '500px' }}
                            renderHTML={(text) => mdParser.render(text)}
                            onChange={({ text }) => setContent(text)}
                            onImageUpload={handleEditorImageUpload}
                            placeholder="Write your post content in markdown..."
                        />
                    </div>

                    <div className="editor-actions">
                        <button
                            type="button"
                            className="btn btn-ghost"
                            onClick={() => navigate(-1)}
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="btn btn-primary"
                            disabled={loading}
                        >
                            {loading ? <span className="spinner-sm"></span> : <><FiSend /> Publish</>}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
