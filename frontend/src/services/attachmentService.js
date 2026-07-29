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

        return `http://127.0.0.1:8000/api/v1/attachments/${id}`;

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