const express = require('express');
const Blog = require('../models/Blog');
const auth = require('../middleware/auth');

const router = express.Router();

// GET /api/blogs — list all blogs
router.get('/', async (req, res) => {
    try {
        const { search, tag, author } = req.query;
        let filter = {};

        if (search) {
            filter.$or = [
                { title: { $regex: search, $options: 'i' } },
                { content: { $regex: search, $options: 'i' } },
            ];
        }
        if (tag) {
            filter.tags = { $in: [tag.toLowerCase()] };
        }
        if (author) {
            filter.author = author;
        }

        const blogs = await Blog.find(filter)
            .populate('author', 'name username profilePicUrl')
            .sort({ createdAt: -1 });

        res.json(blogs);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// GET /api/blogs/bookmarked — user's bookmarked blogs
router.get('/bookmarked', auth, async (req, res) => {
    try {
        const blogs = await Blog.find({ bookmarks: req.user._id })
            .populate('author', 'name username profilePicUrl')
            .sort({ createdAt: -1 });

        res.json(blogs);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// GET /api/blogs/:id — single blog
router.get('/:id', async (req, res) => {
    try {
        const blog = await Blog.findById(req.params.id)
            .populate('author', 'name username profilePicUrl')
            .populate('comments.user', 'name username profilePicUrl');

        if (!blog) {
            return res.status(404).json({ message: 'Blog not found' });
        }

        res.json(blog);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST /api/blogs — create blog
router.post('/', auth, async (req, res) => {
    try {
        const { title, content, coverImage, tags } = req.body;

        const blog = await Blog.create({
            title,
            content,
            coverImage,
            tags: tags || [],
            author: req.user._id,
        });

        const populated = await blog.populate('author', 'name username profilePicUrl');
        res.status(201).json(populated);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// PUT /api/blogs/:id — update blog
router.put('/:id', auth, async (req, res) => {
    try {
        const blog = await Blog.findById(req.params.id);

        if (!blog) {
            return res.status(404).json({ message: 'Blog not found' });
        }

        if (blog.author.toString() !== req.user._id.toString()) {
            return res.status(403).json({ message: 'Not authorized' });
        }

        const { title, content, coverImage, tags } = req.body;
        if (title) blog.title = title;
        if (content) blog.content = content;
        if (coverImage !== undefined) blog.coverImage = coverImage;
        if (tags) blog.tags = tags;

        await blog.save();
        const populated = await blog.populate('author', 'name username profilePicUrl');
        res.json(populated);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// DELETE /api/blogs/:id — delete blog
router.delete('/:id', auth, async (req, res) => {
    try {
        const blog = await Blog.findById(req.params.id);

        if (!blog) {
            return res.status(404).json({ message: 'Blog not found' });
        }

        if (blog.author.toString() !== req.user._id.toString()) {
            return res.status(403).json({ message: 'Not authorized' });
        }

        await blog.deleteOne();
        res.json({ message: 'Blog deleted' });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// PUT /api/blogs/:id/like — toggle like
router.put('/:id/like', auth, async (req, res) => {
    try {
        const blog = await Blog.findById(req.params.id);

        if (!blog) {
            return res.status(404).json({ message: 'Blog not found' });
        }

        const index = blog.likes.indexOf(req.user._id);
        if (index === -1) {
            blog.likes.push(req.user._id);
        } else {
            blog.likes.splice(index, 1);
        }

        await blog.save();
        res.json({ likes: blog.likes, likeCount: blog.likes.length });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST /api/blogs/:id/comment — add comment
router.post('/:id/comment', auth, async (req, res) => {
    try {
        const blog = await Blog.findById(req.params.id);

        if (!blog) {
            return res.status(404).json({ message: 'Blog not found' });
        }

        blog.comments.push({
            user: req.user._id,
            text: req.body.text,
        });

        await blog.save();

        // Populate the new comment's user
        const populated = await blog.populate('comments.user', 'name username profilePicUrl');
        res.status(201).json(populated.comments);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// DELETE /api/blogs/:id/comment/:commentId — delete comment
router.delete('/:id/comment/:commentId', auth, async (req, res) => {
    try {
        const blog = await Blog.findById(req.params.id);

        if (!blog) {
            return res.status(404).json({ message: 'Blog not found' });
        }

        const comment = blog.comments.id(req.params.commentId);
        if (!comment) {
            return res.status(404).json({ message: 'Comment not found' });
        }

        // Only comment author or blog author can delete
        if (
            comment.user.toString() !== req.user._id.toString() &&
            blog.author.toString() !== req.user._id.toString()
        ) {
            return res.status(403).json({ message: 'Not authorized' });
        }

        comment.deleteOne();
        await blog.save();
        res.json({ message: 'Comment deleted' });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// PUT /api/blogs/:id/bookmark — toggle bookmark
router.put('/:id/bookmark', auth, async (req, res) => {
    try {
        const blog = await Blog.findById(req.params.id);

        if (!blog) {
            return res.status(404).json({ message: 'Blog not found' });
        }

        const index = blog.bookmarks.indexOf(req.user._id);
        if (index === -1) {
            blog.bookmarks.push(req.user._id);
        } else {
            blog.bookmarks.splice(index, 1);
        }

        await blog.save();
        res.json({ bookmarks: blog.bookmarks, bookmarked: blog.bookmarks.includes(req.user._id) });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

module.exports = router;
