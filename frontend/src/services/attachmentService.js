import api from "../api/api";

const attachmentService = {

    async upload(messageId, file) {

        const formData = new FormData();

        formData.append("file", file);

        const response = await api.post(

            `/attachments/upload/${messageId}`,

            formData,

            {
                headers: {
                    "Content-Type": "multipart/form-data",
                },
            }

        );

        return response.data;

    },

    downloadUrl(id) {

        const base =
            import.meta.env.VITE_API_URL || "/api/v1";

        return `${base}/attachments/${id}`;

    },

    async getAttachment(id) {

        const response = await api.get(

            `/attachments/${id}`,

            {
                responseType: "blob",
            }

        );

        return URL.createObjectURL(response.data);

    },

};

export default attachmentService;